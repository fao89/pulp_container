# coding=utf-8
"""Tests that sync container plugin repositories."""
import unittest

from pulp_smash import cli, config
from pulp_smash.pulp3.constants import MEDIA_PATH
from pulp_smash.pulp3.utils import delete_orphans, gen_repo

from pulp_container.tests.functional.utils import (
    gen_container_client,
    gen_container_remote,
    monitor_task,
)
from pulp_container.tests.functional.constants import DOCKERHUB_PULP_FIXTURE_1

from pulpcore.client.pulp_container import (
    ContainerContainerRepository,
    ContainerContainerRemote,
    ContentTagsApi,
    RepositoriesContainerApi,
    RepositoriesContainerVersionsApi,
    RepositorySyncURL,
    RemotesContainerApi,
)


class BasicSyncTestCase(unittest.TestCase):
    """Sync repositories with the container plugin."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client_api = gen_container_client()

    def test_sync(self):
        """Sync repositories with the container plugin.

        In order to sync a repository a remote has to be associated within
        this repository. When a repository is created this version field is set
        as None. After a sync the repository version is updated.

        Do the following:

        1. Create a repository, and a remote.
        2. Assert that repository version is None.
        3. Sync the remote.
        4. Assert that repository version is not None.
        5. Sync the remote one more time.
        6. Assert that repository version is the same from the previous one.
        """
        repository_api = RepositoriesContainerApi(self.client_api)
        repository = repository_api.create(ContainerContainerRepository(**gen_repo()))
        self.addCleanup(repository_api.delete, repository.pulp_href)

        remote_api = RemotesContainerApi(self.client_api)
        remote = remote_api.create(gen_container_remote())
        self.addCleanup(remote_api.delete, remote.pulp_href)

        self.assertEqual(repository.latest_version_href, f"{repository.pulp_href}versions/0/")
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)

        # Sync the repository.
        sync_response = repository_api.sync(repository.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)
        repository = repository_api.read(repository.pulp_href)
        self.assertIsNotNone(repository.latest_version_href)

        # Sync the repository again.
        latest_version_href = repository.latest_version_href
        sync_response = repository_api.sync(repository.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)
        repository = repository_api.read(repository.pulp_href)
        self.assertEqual(latest_version_href, repository.latest_version_href)

    def test_file_decriptors(self):
        """Test whether file descriptors are closed properly.

        This test targets the following issue:

        `Pulp #4073 <https://pulp.plan.io/issues/4073>`_

        Do the following:

        1. Check if 'lsof' is installed. If it is not, skip this test.
        2. Create and sync a repo.
        3. Run the 'lsof' command to verify that files in the
           path ``/var/lib/pulp/`` are closed after the sync.
        4. Assert that issued command returns `0` opened files.
        """
        cli_client = cli.Client(self.cfg, cli.echo_handler)

        # check if 'lsof' is available
        if cli_client.run(("which", "lsof")).returncode != 0:
            raise unittest.SkipTest("lsof package is not present")

        repo_api = RepositoriesContainerApi(self.client_api)
        repo = repo_api.create(gen_repo())
        self.addCleanup(repo_api.delete, repo.pulp_href)

        remote_api = RemotesContainerApi(self.client_api)
        remote = remote_api.create(gen_container_remote())
        self.addCleanup(remote_api.delete, remote.pulp_href)

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        cmd = "lsof -t +D {}".format(MEDIA_PATH).split()
        response = cli_client.run(cmd).stdout
        self.assertEqual(len(response), 0, response)


class SyncInvalidURLTestCase(unittest.TestCase):
    """Sync a repository with an invalid url on the Remote."""

    def test_all(self):
        """
        Sync a repository using a Remote url that does not exist.

        Test that we get a task failure.

        """
        client_api = gen_container_client()

        repository_api = RepositoriesContainerApi(client_api)
        repository = repository_api.create(ContainerContainerRepository(**gen_repo()))
        self.addCleanup(repository_api.delete, repository.pulp_href)

        remote_api = RemotesContainerApi(client_api)
        remote_data = gen_container_remote(url="http://i-am-an-invalid-url.com/invalid/")
        remote = remote_api.create(ContainerContainerRemote(**remote_data))
        self.addCleanup(remote_api.delete, remote.pulp_href)

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = repository_api.sync(repository.pulp_href, repository_sync_data)

        task = monitor_task(sync_response.task)
        if isinstance(task, dict):
            self.assertIsNotNone(task["error"]["description"])
        else:
            self.assertFalse("Sync with an invalid remote URL was successful")


class TestRepeatedSync(unittest.TestCase):
    """Test behavior when a sync is repeated."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.client_api = gen_container_client()

        cls.repository_api = RepositoriesContainerApi(cls.client_api)
        cls.from_repo = cls.repository_api.create(ContainerContainerRepository(**gen_repo()))

        cls.remote_api = RemotesContainerApi(cls.client_api)
        remote_data = gen_container_remote(upstream_name=DOCKERHUB_PULP_FIXTURE_1)
        cls.remote = cls.remote_api.create(remote_data)

        delete_orphans()

    @classmethod
    def tearDownClass(cls):
        """Delete things made in setUpClass. addCleanup feature does not work with setupClass."""
        cls.repository_api.delete(cls.from_repo.pulp_href)
        cls.remote_api.delete(cls.remote.pulp_href)
        delete_orphans()

    def test_sync_idempotency(self):
        """Ensure that sync does not create orphan tags https://pulp.plan.io/issues/5252 ."""
        sync_data = RepositorySyncURL(remote=self.remote.pulp_href)
        sync_response = self.repository_api.sync(self.from_repo.pulp_href, sync_data)
        monitor_task(sync_response.task)

        tags_api = ContentTagsApi(self.client_api)
        first_sync_tags_named_a = tags_api.list(name="manifest_a")

        sync_response = self.repository_api.sync(self.from_repo.pulp_href, sync_data)
        monitor_task(sync_response.task)

        second_sync_tags_named_a = tags_api.list(name="manifest_a")

        self.assertEqual(first_sync_tags_named_a.count, 1)
        self.assertEqual(second_sync_tags_named_a.count, 1)


class AllowlistedTagsSyncTestCase(unittest.TestCase):
    """A test case for syncing repositories with allowlisted tags."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        client_api = gen_container_client()
        cls.repositories_api = RepositoriesContainerApi(client_api)
        cls.remotes_api = RemotesContainerApi(client_api)
        cls.tags_api = ContentTagsApi(client_api)
        cls.versions_api = RepositoriesContainerVersionsApi(client_api)

        cls.repository = None

    def test_sync_with_non_existing_allowlisted_tag(self):
        """Check whether the sync machinery ignores a non-existing tag."""
        allowlist_tags = ["manifest_a", "non_existing_manifest"]
        self.sync_repository_with_allowlisted_tags(allowlist_tags)

        self.assert_synced_tags(["manifest_a"])

    def test_sync_with_allowlisted_tags(self):
        """Test whether the repository is synced only with allowlisted tags."""
        allowlist_tags = ["manifest_a", "manifest_b", "manifest_c"]
        self.sync_repository_with_allowlisted_tags(allowlist_tags)

        self.assert_synced_tags(allowlist_tags)

    def test_sync_with_allowlisted_tags_using_wildcard(self):
        """Test whether the repository is synced only with allowlisted tags that use wildcards."""
        allowlist_tags = ["ml_iv", "ml_ii", "manifest_a", "manifest_b",
                          "manifest_c", "manifest_d", "manifest_e"]
        self.sync_repository_with_allowlisted_tags(["ml_??", "manifest*"])

        self.assert_synced_tags(allowlist_tags)

    def sync_repository_with_allowlisted_tags(self, allowlist_tags):
        """Sync a new repository with the allowlisted tags passed as an argument."""
        self.repository = self.repositories_api.create(ContainerContainerRepository(**gen_repo()))
        self.addCleanup(self.repositories_api.delete, self.repository.pulp_href)

        remote_data = gen_container_remote(
            upstream_name=DOCKERHUB_PULP_FIXTURE_1,
            allowlist_tags=allowlist_tags
        )
        remote = self.remotes_api.create(remote_data)
        self.addCleanup(self.remotes_api.delete, remote.pulp_href)

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)

        sync_response = self.repositories_api.sync(self.repository.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)
        repository = self.repositories_api.read(self.repository.pulp_href)
        self.assertIsNotNone(repository.latest_version_href)

    def assert_synced_tags(self, allowlist_tags):
        """Check if the created repository contains only the selected allowlisted tags."""
        latest_repo_version = self.repositories_api.read(
            self.repository.pulp_href
        ).latest_version_href
        tags = self.tags_api.list(repository_version=latest_repo_version).results

        self.assertEqual(sorted(tag.name for tag in tags), sorted(allowlist_tags))
