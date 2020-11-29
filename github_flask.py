import os
import hmac
from flask import abort, jsonify, request
from github_app import GithubApp
from six import ensure_binary

STATUS_FUNC_CALLED = "HIT"
STATUS_NO_FUNC_CALLED = "MISS"


class GithubAppFlask(object):
    def __init__(self, app):
        self.app = app

        if app is not None:
            app.add_url_rule(
                app.config.get("GITHUB_APP_ROUTE", "/"),
                view_func=self._flask_view_func,
                methods=["POST"],
            )

        self._hook_mappings = {}

    @property
    def github_app_installation(self):
        return self.github_app.get_installation(installation_id=self.payload["installation"]["id"])

    @property
    def github_app(self):
        return GithubApp(
            self.app.config.get("GITHUB_APP_ID"),
            self.app.config.get("GITHUB_KEY_FILE"),
            self.app.config.get("GITHUB_SECRET"),
        )

    @property
    def payload(self):
        """GitHub hook payload"""
        if request and request.json and "installation" in request.json:
            return request.json

        raise RuntimeError("Payload is only available in the context of a GitHub hook request")

    def on(self, event_actions):
        """Decorator routes a GitHub hook to the wrapped function.
        Functions decorated as a hook recipient are registered as the function for the given GitHub event.

        @github_app.on(['issues.opened'])
        def cruel_closer():
            owner = github_app.payload['repository']['owner']['login']
            repo = github_app.payload['repository']['name']
            num = github_app.payload['issue']['id']
            issue = github_app.installation_client.issue(owner, repo, num)
            issue.create_comment('Could not replicate.')
            issue.close()

        Arguments:
            event_action {List[str]} -- Name of the event and optional action (separated by a period), e.g. 'issues.opened' or
                'pull_request'
        """

        def decorator(f):
            for event_action in event_actions:
                if event_action not in self._hook_mappings:
                    self._hook_mappings[event_action] = [f]
                else:
                    self._hook_mappings[event_action].append(f)

            # make sure the function can still be called normally (e.g. if a user wants to pass in their
            # own Context for whatever reason).
            return f

        return decorator

    def _flask_view_func(self):
        functions_to_call = []
        calls = {}

        event = request.headers["X-GitHub-Event"]
        action = request.json.get("action")

        self._verify_webhook()

        if event in self._hook_mappings:
            functions_to_call += self._hook_mappings[event]

        if action:
            event_action = ".".join([event, action])
            if event_action in self._hook_mappings:
                functions_to_call += self._hook_mappings[event_action]

        if functions_to_call:
            for function in functions_to_call:
                calls[function.__name__] = function()
            status = STATUS_FUNC_CALLED
        else:
            status = STATUS_NO_FUNC_CALLED
        return jsonify({"status": status, "calls": calls})

    def _verify_webhook(self):
        signature = request.headers["X-Hub-Signature"].split("=")[1]

        mac = hmac.new(ensure_binary(self.github_app.app_secret), msg=request.data, digestmod="sha1")

        if not hmac.compare_digest(mac.hexdigest(), signature):
            # LOG.warning("GitHub hook signature verification failed.")
            abort(400)
