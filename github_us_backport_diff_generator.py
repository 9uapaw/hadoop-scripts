import argparse
import datetime
import errno
import logging
import os
import re
from collections import namedtuple
from os.path import expanduser
from typing import List
import requests
import sh as sh

COMMIT_MESSAGE_PREFIX = "Subject"
COMMIT_JIRA_REGEX = re.compile(".*?(YARN-\d+|HADOOP-\d+).*")
PATH_PREFIX = "diff --git"

VAR_PLACEHOLDER = "$$"
GITHUB_PR_PATCH_URL_TEMPLATE = f"https://github.com/apache/hadoop/pull/{VAR_PLACEHOLDER}.patch"
GITHUB_PR_DIFF_URL_TEMPLATE = f"https://github.com/apache/hadoop/pull/{VAR_PLACEHOLDER}.diff"
LOG = logging.getLogger(__name__)

UpstreamJira = namedtuple('UpstreamJira', ['diff', 'patch'])


def get_github_patch_url(pr_id):
    return GITHUB_PR_PATCH_URL_TEMPLATE.replace(VAR_PLACEHOLDER, pr_id)


def get_github_diff_url(pr_id):
    return GITHUB_PR_DIFF_URL_TEMPLATE.replace(VAR_PLACEHOLDER, pr_id)


def join_path(*components):
    if components and components[0] and not components[0].startswith(os.sep) and not components[0].startswith("~"):
        lst = list(components)
        lst[0] = os.sep + components[0]
        components = tuple(lst)
    return os.path.join(*components)


def ensure_dir_created(dirname, log_exception=False):
    """
    Ensure that a named directory exists; if it does not, attempt to create it.
    """
    try:
        os.makedirs(dirname)
    except OSError as e:
        if log_exception:
            LOG.exception("Failed to create dirs", exc_info=True)
        # If Errno is File exists, don't raise Exception
        if e.errno != errno.EEXIST:
            raise
    return dirname


def download_file(url, dest_file):
    # NOTE the stream=True parameter below
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                #if chunk:
                f.write(chunk)
    return dest_file


def get_date_formatted():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def extract_jira_and_paths_from_patch_file(pr_id, patch_file):
    print("Extracting information from patch file {} for PR {}".format(patch_file, pr_id))
    paths = []

    with open(patch_file, 'r') as file:
        content = file.readlines()
        for line in content:
            if line.startswith(COMMIT_MESSAGE_PREFIX):
                if COMMIT_JIRA_REGEX.match(line):
                    jira = COMMIT_JIRA_REGEX.match(line).groups()[0]
            elif line.startswith(PATH_PREFIX):
                path = line.lstrip(PATH_PREFIX).split(" ")[0].lstrip("a/ ")
                if path:
                    paths.append(path)
    return jira, paths


def validate_pr_ids(pr_ids: List[str]):
    regex = re.compile('\d+', re.I)
    for pr_id in pr_ids:
        match = regex.match(pr_id)
        if not bool(match):
            raise ValueError("Invalid GitHub PR ID specified: {}".format(pr_id))


def process(pr_ids: List[str], timestamp: str):
    home = expanduser("~")
    script_workspace_dir = join_path(home, "github_us_diff_generator")
    script_html_out_dir = join_path(home, "github_us_diff_generator", "html")
    ensure_dir_created(script_workspace_dir)
    ensure_dir_created(script_html_out_dir)
    validate_pr_ids(pr_ids)

    pr_id_to_files = {}
    for pr_id in pr_ids:
        pr_dir = join_path(script_workspace_dir, pr_id)
        ensure_dir_created(pr_dir)

        pr_id_to_files[pr_id] = {}
        full_github_patch_url = get_github_patch_url(pr_id)
        full_github_diff_url = get_github_diff_url(pr_id)

        print("Downloading Github PR patch file: {}".format(full_github_patch_url))
        patch_file = download_file(full_github_patch_url, join_path(pr_dir, f"{pr_id}_{timestamp}.patch"))

        print("Downloading Github PR diff file: {}".format(full_github_diff_url))
        diff_file = download_file(full_github_diff_url, join_path(pr_dir, f"{pr_id}_{timestamp}.diff"))
        pr_id_to_files[pr_id] = UpstreamJira(diff_file, patch_file)

    print("Downloaded files: " + str(pr_id_to_files))

    jira_ids = set()
    jira_id = None
    for pr_id, jira in pr_id_to_files.items():  # type: str, UpstreamJira
        # Determine jira ID from patch file
        jira_id, paths = extract_jira_and_paths_from_patch_file(pr_id, jira.patch)
        jira_ids.add(jira_id)
        if len(jira_ids) > 1:
            raise ValueError("Expected Github PRs to belong to one single jira. Multiple Jira IDs found: %s".format(jira_ids))

    if not jira_id:
        raise ValueError("Jira ID not found!")

    diff_pairs = [(pr_ids[0], i) for i in pr_ids[1:]]
    print("PR diffs will be created for: {}".format(diff_pairs))
    diff_files = [(pr_id_to_files[pr1].diff, pr_id_to_files[pr2].diff) for pr1, pr2 in diff_pairs]
    for file1, file2 in diff_files:
        file_1_pr_id = os.path.basename(file1).split("_")[0]
        file_2_pr_id = os.path.basename(file2).split("_")[0]
        html_name = f"{file_1_pr_id}-{file_2_pr_id}_{jira_id}.html"
        html_full_path = join_path(script_html_out_dir, html_name)
        print("Creating diff of files: {}, {}".format(file1, file2))

        # EXAMPLE full command:
        # vim $HOME/version1.diff $HOME/version2.diff -d -c TOhtml -c 'w! /tmp/html' -c qa!
        vim = sh.vim(file1, file2, "-d", "-c", "TOhtml", "-c", f"\"w! {html_full_path}\"", "-c", "diffoff!", "-c", "qa!")
        print("Created diff HTML file: {}".format(html_full_path))

        # UNCOMMENT THIS TO PRINT THE COMMAND WAS RUNNING
        # print(vim.cmd)
        # print(vim.call_args)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("github_pr_ids", nargs="*")
    parser.add_argument("--file")
    args = parser.parse_args()
    github_pr_ids = args.github_pr_ids

    if args.file:
        with open(args.file, 'r') as f:
            github_pr_ids = f.readlines()

    timestamp = get_date_formatted()
    process(github_pr_ids, timestamp)

