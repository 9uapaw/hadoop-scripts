import argparse
import os
import re
import shutil
from pprint import pprint

import sh
from typing import List
from zipfile import ZipFile
import requests

PATCH_ZIP = "patch?zip"
COMMIT_MESSAGE_PREFIX = "Subject"
COMMIT_JIRA_REGEX = re.compile(".*?(YARN-\d+|HADOOP-\d+).*")
PATH_PREFIX = "diff --git"
GITHUB_COMMIT_API = "https://api.github.com/repos/apache/hadoop/commits"
GITHUB_COMMIT_URL_TEMPLATE = "https://github.com/apache/hadoop/commit/{sha}.diff"
PATH_LIMIT = 20


def download_file(url):
    local_filename = url.split('/')[-1]
    with requests.get(url) as r:
        with open(local_filename, 'w') as f:
            f.write(r.text)

    return local_filename

def process(revision: str):
    revision: List[str] = revision.split("/")
    revision_no = revision[0]
    patch_set = revision[1]

    print("Downloading revision {}".format(revision_no))
    sh.curl("-L", "-O", "https://gerrit.sjc.cloudera.com/changes/cdh%2Fhadoop~{revision}/revisions/{patch_set}/patch?zip".format(revision=revision_no, patch_set=patch_set))

    with ZipFile(PATCH_ZIP, 'r') as zip:
        gerrit_file = zip.filelist[0].filename
        zip.extractall()

    jira = ""
    os.remove(PATCH_ZIP)
    print("Extracting information from gerrit file {}".format(gerrit_file))
    paths = []

    with open(gerrit_file, 'r') as file:
        content = file.readlines()
        for line in content:
            if line.startswith(COMMIT_MESSAGE_PREFIX):
                jira = COMMIT_JIRA_REGEX.match(line).groups()[0]
            elif line.startswith(PATH_PREFIX):
                path = line.lstrip(PATH_PREFIX).split(" ")[0].lstrip("a/ ")
                if path:
                    paths.append(path)

    if len(paths) > PATH_LIMIT:
        paths = paths[:PATH_LIMIT]

    upstream_commit_candidates = requests.get(GITHUB_COMMIT_API, params={"path": paths}).json()
    upstream_commit = ""
    for commit in upstream_commit_candidates:
        if commit['commit']['message'].startswith(jira):
            upstream_commit = commit['sha']

    if upstream_commit:
        print("Found {} upstream commit: {}".format(jira, upstream_commit))
    else:
        return False

    print("Downloading upstream commit {}".format(upstream_commit))
    download_file(GITHUB_COMMIT_URL_TEMPLATE.format(sha=upstream_commit))
    html_name = f"{revision[0]}-{revision[1]}_{jira}"

    vim = sh.vim("-d", "-c", "TOhtml", "-c", "w! {}.html".format(html_name), "-c", "qa!", gerrit_file, "{}.diff".format(upstream_commit))

    os.remove(gerrit_file)
    os.remove("{}.diff".format(upstream_commit))

    print("Created diff HTML {}.html".format(html_name))
    # UNCOMMENT THIS TO PRINT THE COMMAND WAS RUNNING
    # print(vim.cmd)
    # print(vim.call_args)

    return True


if __name__ == "__main__":
    """
    Example usage: backport-diff-generator 140697/1
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", nargs="*")
    parser.add_argument("--file")
    args = parser.parse_args()
    revisions = args.revision
    rev_copy = revisions.copy()

    if args.file:
        with open(args.file, 'r') as f:
            revisions = f.readlines()

    for i, rev in enumerate(rev_copy):
        if "-" in rev:
            start, end = rev.split("-")
            start_num = int(start.split("/")[0])
            end_num = int(end.split("/")[0])
            revisions.remove(rev)
            revisions.extend([f"{i}/1" for i in range(start_num, end_num + 1)])

    unsuccessful = []
    for rev in revisions:
        if not process(rev):
            unsuccessful.append(rev)

    if unsuccessful:
        print("Unsuccessful revision comparison:")
        [print(rev) for rev in unsuccessful]
    else:
        print("All revision comparison generation were successful")
