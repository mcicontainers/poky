#! /usr/bin/env python3
#
# BitBake Toaster Implementation
#
# Copyright (C) 2013-2016 Intel Corporation
#
# SPDX-License-Identifier: GPL-2.0-only
#

import re, time

from django.urls import reverse
from django.utils import timezone
from bldcontrol.models import BuildRequest
from tests.browser.selenium_helpers import SeleniumTestCase

from orm.models import BitbakeVersion, Layer, Layer_Version, Recipe, Release, Project, Build, Target, Task

from selenium.webdriver.common.by import By


class TestAllBuildsPage(SeleniumTestCase):
    """ Tests for all builds page /builds/ """

    PROJECT_NAME = 'test project'
    CLI_BUILDS_PROJECT_NAME = 'command line builds'

    def setUp(self):
        bbv = BitbakeVersion.objects.create(name='bbv1', giturl='/tmp/',
                                            branch='master', dirpath='')
        release = Release.objects.create(name='release1',
                                         bitbake_version=bbv)
        self.project1 = Project.objects.create_project(name=self.PROJECT_NAME,
                                                       release=release)
        self.default_project = Project.objects.create_project(
            name=self.CLI_BUILDS_PROJECT_NAME,
            release=release
        )
        self.default_project.is_default = True
        self.default_project.save()

        # parameters for builds to associate with the projects
        now = timezone.now()

        self.project1_build_success = {
            'project': self.project1,
            'started_on': now,
            'completed_on': now,
            'outcome': Build.SUCCEEDED
        }

        self.project1_build_failure = {
            'project': self.project1,
            'started_on': now,
            'completed_on': now,
            'outcome': Build.FAILED
        }

        self.default_project_build_success = {
            'project': self.default_project,
            'started_on': now,
            'completed_on': now,
            'outcome': Build.SUCCEEDED
        }

    def _get_build_time_element(self, build):
        """
        Return the HTML element containing the build time for a build
        in the recent builds area
        """
        selector = 'div[data-latest-build-result="%s"] ' \
            '[data-role="data-recent-build-buildtime-field"]' % build.id

        # because this loads via Ajax, wait for it to be visible
        self.wait_until_present(selector)

        build_time_spans = self.find_all(selector)

        self.assertEqual(len(build_time_spans), 1)

        return build_time_spans[0]

    def _get_row_for_build(self, build):
        """ Get the table row for the build from the all builds table """
        self.wait_until_present('#allbuildstable')

        rows = self.find_all('#allbuildstable tr')

        # look for the row with a download link on the recipe which matches the
        # build ID
        url = reverse('builddashboard', args=(build.id,))
        selector = 'td.target a[href="%s"]' % url

        found_row = None
        for row in rows:

            outcome_links = row.find_elements(By.CSS_SELECTOR, selector)
            if len(outcome_links) == 1:
                found_row = row
                break

        self.assertNotEqual(found_row, None)

        return found_row

    def _get_create_builds(self, **kwargs):
        """ Create a build and return the build object """
        build1 = Build.objects.create(**self.project1_build_success)
        build2 = Build.objects.create(**self.project1_build_failure)

        # add some targets to these builds so they have recipe links
        # (and so we can find the row in the ToasterTable corresponding to
        # a particular build)
        Target.objects.create(build=build1, target='foo')
        Target.objects.create(build=build2, target='bar')

        if kwargs:
            # Create kwargs.get('success') builds with success status with target
            # and kwargs.get('failure') builds with failure status with target
            for i in range(kwargs.get('success', 0)):
                now = timezone.now()
                self.project1_build_success['started_on'] = now
                self.project1_build_success[
                    'completed_on'] = now - timezone.timedelta(days=i)
                build = Build.objects.create(**self.project1_build_success)
                Target.objects.create(build=build,
                                      target=f'{i}_success_recipe',
                                      task=f'{i}_success_task')

                self._set_buildRequest_and_task_on_build(build)
            for i in range(kwargs.get('failure', 0)):
                now = timezone.now()
                self.project1_build_failure['started_on'] = now
                self.project1_build_failure[
                    'completed_on'] = now - timezone.timedelta(days=i)
                build = Build.objects.create(**self.project1_build_failure)
                Target.objects.create(build=build,
                                      target=f'{i}_fail_recipe',
                                      task=f'{i}_fail_task')
                self._set_buildRequest_and_task_on_build(build)
        return build1, build2

    def _create_recipe(self):
        """ Add a recipe to the database and return it """
        layer = Layer.objects.create()
        layer_version = Layer_Version.objects.create(layer=layer)
        return Recipe.objects.create(name='recipe_foo', layer_version=layer_version)

    def _set_buildRequest_and_task_on_build(self, build):
        """ Set buildRequest and task on build """
        build.recipes_parsed = 1
        build.save()
        buildRequest = BuildRequest.objects.create(
            build=build, 
            project=self.project1,
            state=BuildRequest.REQ_COMPLETED)
        build.build_request = buildRequest
        recipe = self._create_recipe()
        task = Task.objects.create(build=build,
                                   recipe=recipe, 
                                   task_name='task',
                                   outcome=Task.OUTCOME_SUCCESS)
        task.save()
        build.save()

    def test_show_tasks_with_suffix(self):
        """ Task should be shown as suffix on build name """
        build = Build.objects.create(**self.project1_build_success)
        target = 'bash'
        task = 'clean'
        Target.objects.create(build=build, target=target, task=task)

        url = reverse('all-builds')
        self.get(url)
        self.wait_until_present('td[class="target"]')

        cell = self.find('td[class="target"]')
        content = cell.get_attribute('innerHTML')
        expected_text = '%s:%s' % (target, task)

        self.assertTrue(re.search(expected_text, content),
                        '"target" cell should contain text %s' % expected_text)

    def test_rebuild_buttons(self):
        """
        Test 'Rebuild' buttons in recent builds section

        'Rebuild' button should not be shown for command-line builds,
        but should be shown for other builds
        """
        build1 = Build.objects.create(**self.project1_build_success)
        default_build = Build.objects.create(**self.default_project_build_success)

        url = reverse('all-builds')
        self.get(url)

        # should see a rebuild button for non-command-line builds
        selector = 'div[data-latest-build-result="%s"] .rebuild-btn' % build1.id
        time.sleep(2)
        run_again_button = self.find_all(selector)
        self.assertEqual(len(run_again_button), 1,
                         'should see a rebuild button for non-cli builds')

        # shouldn't see a rebuild button for command-line builds
        selector = 'div[data-latest-build-result="%s"] .rebuild-btn' % default_build.id
        run_again_button = self.find_all(selector)
        self.assertEqual(len(run_again_button), 0,
                         'should not see a rebuild button for cli builds')

    def test_tooltips_on_project_name(self):
        """
        Test tooltips shown next to project name in the main table

        A tooltip should be present next to the command line
        builds project name in the all builds page, but not for
        other projects
        """
        Build.objects.create(**self.project1_build_success)
        Build.objects.create(**self.default_project_build_success)

        url = reverse('all-builds')
        self.get(url)

        # get the project name cells from the table
        cells = self.find_all('#allbuildstable td[class="project"]')

        selector = 'span.get-help'

        for cell in cells:
            content = cell.get_attribute('innerHTML')
            help_icons = cell.find_elements_by_css_selector(selector)

            if re.search(self.PROJECT_NAME, content):
                # no help icon next to non-cli project name
                msg = 'should not be a help icon for non-cli builds name'
                self.assertEqual(len(help_icons), 0, msg)
            elif re.search(self.CLI_BUILDS_PROJECT_NAME, content):
                # help icon next to cli project name
                msg = 'should be a help icon for cli builds name'
                self.assertEqual(len(help_icons), 1, msg)
            else:
                msg = 'found unexpected project name cell in all builds table'
                self.fail(msg)

    def test_builds_time_links(self):
        """
        Successful builds should have links on the time column and in the
        recent builds area; failed builds should not have links on the time column,
        or in the recent builds area
        """
        build1, build2 = self._get_create_builds()

        url = reverse('all-builds')
        self.get(url)

        # test recent builds area for successful build
        element = self._get_build_time_element(build1)
        links = element.find_elements(By.CSS_SELECTOR, 'a')
        msg = 'should be a link on the build time for a successful recent build'
        self.assertEquals(len(links), 1, msg)

        # test recent builds area for failed build
        element = self._get_build_time_element(build2)
        links = element.find_elements(By.CSS_SELECTOR, 'a')
        msg = 'should not be a link on the build time for a failed recent build'
        self.assertEquals(len(links), 0, msg)

        # test the time column for successful build
        build1_row = self._get_row_for_build(build1)
        links = build1_row.find_elements(By.CSS_SELECTOR, 'td.time a')
        msg = 'should be a link on the build time for a successful build'
        self.assertEquals(len(links), 1, msg)

        # test the time column for failed build
        build2_row = self._get_row_for_build(build2)
        links = build2_row.find_elements(By.CSS_SELECTOR, 'td.time a')
        msg = 'should not be a link on the build time for a failed build'
        self.assertEquals(len(links), 0, msg)

    def test_builds_table_search_box(self):
        """ Test the search box in the builds table on the all builds page """
        self._get_create_builds()

        url = reverse('all-builds')
        self.get(url)

        # Check search box is present and works
        self.wait_until_present('#allbuildstable tbody tr')
        search_box = self.find('#search-input-allbuildstable')
        self.assertTrue(search_box.is_displayed())

        # Check that we can search for a build by recipe name
        search_box.send_keys('foo')
        search_btn = self.find('#search-submit-allbuildstable')
        search_btn.click()
        self.wait_until_present('#allbuildstable tbody tr')
        rows = self.find_all('#allbuildstable tbody tr')
        self.assertTrue(len(rows) >= 1)

    def test_filtering_on_failure_tasks_column(self):
        """ Test the filtering on failure tasks column in the builds table on the all builds page """
        self._get_create_builds(success=10, failure=10)

        url = reverse('all-builds')
        self.get(url)

        # Check filtering on failure tasks column
        self.wait_until_present('#allbuildstable tbody tr')
        failed_tasks_filter = self.find('#failed_tasks_filter')
        failed_tasks_filter.click()
        # Check popup is visible
        time.sleep(1)
        self.wait_until_present('#filter-modal-allbuildstable')
        self.assertTrue(self.find('#filter-modal-allbuildstable').is_displayed())
        # Check that we can filter by failure tasks
        build_without_failure_tasks = self.find('#failed_tasks_filter\\:without_failed_tasks')
        build_without_failure_tasks.click()
        # click on apply button
        self.find('#filter-modal-allbuildstable .btn-primary').click()
        self.wait_until_present('#allbuildstable tbody tr')
        # Check if filter is applied, by checking if failed_tasks_filter has btn-primary class
        self.assertTrue(self.find('#failed_tasks_filter').get_attribute('class').find('btn-primary') != -1)

    def test_filtering_on_completedOn_column(self):
        """ Test the filtering on completed_on column in the builds table on the all builds page """
        self._get_create_builds(success=10, failure=10)

        url = reverse('all-builds')
        self.get(url)

        # Check filtering on failure tasks column
        self.wait_until_present('#allbuildstable tbody tr')
        completed_on_filter = self.find('#completed_on_filter')
        completed_on_filter.click()
        # Check popup is visible
        time.sleep(1)
        self.wait_until_present('#filter-modal-allbuildstable')
        self.assertTrue(self.find('#filter-modal-allbuildstable').is_displayed())
        # Check that we can filter by failure tasks
        build_without_failure_tasks = self.find('#completed_on_filter\\:date_range')
        build_without_failure_tasks.click()
        # click on apply button
        self.find('#filter-modal-allbuildstable .btn-primary').click()
        self.wait_until_present('#allbuildstable tbody tr')
        # Check if filter is applied, by checking if completed_on_filter has btn-primary class
        self.assertTrue(self.find('#completed_on_filter').get_attribute('class').find('btn-primary') != -1)
        
        # Filter by date range
        self.find('#completed_on_filter').click()
        self.wait_until_present('#filter-modal-allbuildstable')
        date_ranges = self.driver.find_elements(
            By.XPATH, '//input[@class="form-control hasDatepicker"]')
        today = timezone.now()
        yestersday = today - timezone.timedelta(days=1)
        time.sleep(1)
        date_ranges[0].send_keys(yestersday.strftime('%Y-%m-%d'))
        date_ranges[1].send_keys(today.strftime('%Y-%m-%d'))
        self.find('#filter-modal-allbuildstable .btn-primary').click()
        self.wait_until_present('#allbuildstable tbody tr')
        self.assertTrue(self.find('#completed_on_filter').get_attribute('class').find('btn-primary') != -1)
        # Check if filter is applied, number of builds displayed should be 6
        time.sleep(1)
        self.assertTrue(len(self.find_all('#allbuildstable tbody tr')) == 6)

