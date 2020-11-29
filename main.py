import config
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

        # Mark the check run as complete!
        check_run.edit(
            name=APP_NAME,
            status="completed",
            started_at=datetime.now(),
            conclusion="success",
        )


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
