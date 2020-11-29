import os
import time
import jwt
import re
import requests
from github import Github
from datetime import datetime, timedelta


# Used by both the GithubApp and GithubAppInstall classes for pagination.
def get_link_from_response(response):
    if "Link" in response.headers:
        regex = r"\<https://api.github.com/([^>]*)\>; rel=\"([a-z]*)\""
        groups = re.findall(regex, response.headers["Link"])
        for group in groups:
            if group[1] == "next":
                return "https://api.github.com/%s" % (group[0])
    return False


class GithubApp(object):
    """[summary]

    Args:
        object ([type]): [description]
    """

    def __init__(self, app_id, app_key_file, app_secret):
        if not os.path.isfile(app_key_file):
            raise ValueError("Github Application Key not exists.")
        self.app_id = app_id
        self.app_key_file = app_key_file
        self.app_secret = app_secret

    @property
    def user_agent(self):
        return "github_app"

    def get_jwt(self):
        with open(self.app_key_file, "r") as keyfile:
            private_key = keyfile.read()

        now = int(time.time())
        payload = {
            # issued at time
            "iat": now,
            # JWT expiration time (10 minute maximum, set to nine in case of crappy clocks)
            "exp": now + (9 * 60),
            # GitHub App's identifier
            "iss": self.app_id,
        }
        return jwt.encode(payload, private_key, algorithm="RS256").decode("utf-8")

    def get_installation(self, installation_id):
        return GithubAppInstallation(self, installation_id)

    def request(self, url, method="GET"):
        if method == "GET":
            requestfunc = requests.get
        elif method == "POST":
            requestfunc = requests.post
        app_token = self.get_jwt()

        headers = {
            "Authorization": "Bearer %s" % (app_token,),
            "Accept": "application/vnd.github.machine-man-preview+json",
            "User-Agent": self.user_agent,
        }
        response = requestfunc("https://api.github.com/%s" % (url,), headers=headers)
        response.raise_for_status()
        retobj = response.json()

        nextpage = get_link_from_response(response)
        if nextpage:
            nextresults = self.request(nextpage)
            retobj += nextresults
        return retobj


tokens = {}


class GithubAppInstallation(object):
    def __init__(self, app, installation_id):
        self.app = app
        self.installation_id = installation_id

    @property
    def token(self):
        if self.installation_id in tokens:
            expiration = tokens[self.installation_id]["expires_at"]
            testtime = datetime.now() - timedelta(minutes=3)
            exptime = datetime.strptime(expiration, "%Y-%m-%dT%H:%M:%SZ")
            if exptime > testtime:
                return tokens[self.installation_id]["token"]

        url = "app/installations/%s/access_tokens" % (self.installation_id,)
        tokens[self.installation_id] = self.app.request(url, "POST")
        return tokens[self.installation_id]["token"]

    def request(self, url):
        client = self.get_github_client()
        headers = {"Accept": "application/vnd.github.machine-man-preview+json"}
        res = client._get(url, headers=headers)
        res.raise_for_status()
        return res

    def get_details(self):
        return self.app.request("app/installations/%s" % (self.installation_id,))

    def get_github_client(self):
        gh = Github(self.token, user_agent=self.app.user_agent)
        # gh.set_user_agent(self.app.user_agent)
        return gh

    def get_repositories(self, url=False):
        if not url:
            url = "https://api.github.com/installation/repositories"
        res = self.request(url)
        repodata = res.json()
        repos = [repo["full_name"] for repo in repodata["repositories"]]

        # Recursively load the next pages, if there are any.
        nextpage = get_link_from_response(res)
        if nextpage:
            repos += self.get_repositories(nextpage)
        return repos

    def get_pr_numbers(self, user, repo):
        repository = self.get_repository(user, repo).repository
        prs = repository.pull_requests(state="open")
        return [pr.number for pr in prs]
