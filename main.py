import subprocess
from tempfile import tempdir
import config
import git
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask
from github_flask import GithubAppFlask


app = Flask(__name__)
APP_NAME = "Octo PyLinter"

app.config["GITHUB_APP_ID"] = config.GITHUB_APP_ID
app.config["GITHUB_KEY_FILE"] = config.GITHUB_KEY_FILE
app.config["GITHUB_SECRET"] = config.GITHUB_SECRET
app.config["GITHUB_APP_ROUTE"] = config.GITHUB_APP_ROUTE

github_app = GithubAppFlask(app)


@github_app.on(
    [
        "check_suite.requested",
        "check_suite.rerequested",
        "check_run.rerequested",
    ]
)
def create_check_run():
    client = github_app.github_app_installation.get_github_client()
    head_sha = (
        github_app.payload["check_run"]
        if "check_run" in github_app.payload
        else github_app.payload["check_suite"]["head_sha"]
    )
    repo = client.get_repo(github_app.payload["repository"]["full_name"])
    repo.create_check_run(name=APP_NAME, head_sha=head_sha)


@github_app.on(["check_run.created"])
def initiate_check_run():
    """Start the CI process"""

    # Check that the event is being sent to this app
    if str(github_app.payload["check_run"]["app"]["id"]) == config.GITHUB_APP_ID:
        client = github_app.github_app_installation.get_github_client()
        repo = client.get_repo(github_app.payload["repository"]["full_name"])
        check_run = repo.get_check_run(github_app.payload["check_run"]["id"])
        # Mark the check run as in process
        check_run.edit(
            name=APP_NAME,
            status="in_progress",
            started_at=datetime.now(),
        )

        # ***** RUN A CI TEST *****
        full_repo_name = github_app.payload["repository"]["full_name"]
        repository = github_app.payload["repository"]["name"]
        head_sha = github_app.payload["check_run"]["head_sha"]
        repo_dir = clone_repository(
            full_repo_name,
            repository,
            head_sha,
            installation_token=github_app.github_app_installation.token,
        )

        command = f"pylint {repo_dir}/{repository}/**/*.py -f json"
        report = subprocess.getoutput(command)
        shutil.rmtree(repo_dir)
        output = json.loads(report)
        # lint
        max_annotations = 50

        annotations = []

        # RuboCop reports the number of errors found in "offense_count"
        if len(output) == 0:
            conclusion = "success"
            actions = None
        else:
            conclusion = "neutral"
            for file in output:

                file_path = re.sub(f"/{repo_dir}\/{repository}\//", "", file["path"])
                annotation_level = "notice"

                # Parse each offense to get details and location
                # Limit the number of annotations to 50
                if max_annotations == 0:
                    break
                max_annotations -= 1

                start_line = file["line"]
                end_line = file["line"]
                start_column = file["column"]
                end_column = file["column"]
                message = file["message"]

                # Create a new annotation for each error
                annotation = {
                    "path": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "start_column": start_column,
                    "end_column": end_column,
                    "annotation_level": annotation_level,
                    "message": message,
                }
                # # Annotations only support start and end columns on the same line
                # if start_line == end_line:
                #     annotation.merge({"start_column": start_column, "end_column": end_column})

                annotations.append(annotation)
            # Need fix action
            actions = [
                {
                    "label": "Fix this",
                    "description": "Automatically fix all linter notices.",
                    "identifier": "fix_rubocop_notices",
                }
            ]
        summary = (
            f"Summary\n"
            f"- Offense count: {len(output)}\n"
            f"- File count: {len(set([file['path'] for file in output]))}\n"
        )
        text = "Octo Pylinter version: pylint"
        # Mark the check run as complete!
        check_run.edit(
            name=APP_NAME,
            status="completed",
            completed_at=datetime.now(),
            conclusion=conclusion,
            output={
                "title": "Octo Pylinter",
                "summary": summary,
                "text": text,
                "annotations": annotations,
            },
            actions=actions,
        )


@github_app.on(["check_run.requested_action"])
def take_requested_action():
    full_repo_name = github_app.payload["repository"]["full_name"]
    repository = github_app.payload["repository"]["name"]
    head_branch = github_app.payload["check_run"]["check_suite"]["head_branch"]

    if github_app.payload["requested_action"]["identifier"] == "fix_rubocop_notices":
        repo_dir = clone_repository(
            full_repo_name,
            repository,
            head_branch,
            installation_token=github_app.github_app_installation.token,
        )

        # Automatically correct RuboCop style errors
        # TODO: fix comand
        command = f"pylint {repo_dir}/{repository}/**/*.py -f json"
        report = subprocess.getoutput(command)

        # output = json.loads(report)
        try:
            repo = git.Repo(f"{repo_dir}/{repository}")
            repo.config_writer().set_value("user", "name", config.GITHUB_APP_USER_NAME).release()
            repo.config_writer().set_value("user", "email", config.GITHUB_APP_USER_EMAIL).release()
            repo.git.add(update=True)
            repo.index.commit("Automatically fix Octo RuboCop notices.")
            origin = repo.remote(name="origin")
            origin.push()
        except:
            print("failed to commit and push")
            # # Nothing to commit!
            # print("Nothing to commit")
        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)


def clone_repository(full_repo_name, repository, ref, installation_token, clean=False):
    repo_dir = tempfile.mkdtemp()
    git.Git(repo_dir).clone(f"https://x-access-token:{installation_token}@github.com/{full_repo_name}.git")
    # TODO: fix pull and chekout
    repo = git.Repo(f"{repo_dir}/{repository}")
    repo.pull()
    repo.checkout(ref)
    if clean:
        shutil.rmtree(tempdir, ignore_errors=True)
    return repo_dir


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
