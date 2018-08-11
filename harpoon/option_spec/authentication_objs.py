from harpoon.amazon import assume_role, decrypt_kms, get_s3_slip

from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj

from six.moves.urllib.parse import urlparse
import subprocess
import urllib3
import logging
import time
import six
import os

log = logging.getLogger("harpoon.option_spec.authentication_objs")

class Authentication(dictobj):
    fields = ["registries"]

    def login(self, docker_api, image_name, is_pushing=False, global_docker=False):
        registry = urlparse("https://{0}".format(image_name)).netloc

        username = None
        if registry in self.registries:
            if is_pushing:
                authenticator = self.registries[registry]['writing']
            else:
                authenticator = self.registries[registry]['reading']

            if authenticator is not NotSpecified:
                username, password = authenticator.creds

        if username is not None:
            if global_docker:
                # First work out if docker login supports --email
                # If it does we must supply it otherwise it will prompt the user for it
                # If it doesn't support --email then we can't supply it....
                process = subprocess.Popen(["docker", "login", "--help"], stdout=subprocess.PIPE)
                out, _ = process.communicate()
                if isinstance(out, six.binary_type):
                    out = out.decode()

                if "-e, --email" in out:
                    cmd = "docker login -u {0} -p {1} -e emailnotneeded@goawaydocker.com {2}".format(username, password, registry)
                else:
                    cmd = "docker login -u {0} -p {1} {2}".format(username, password, registry)
                os.system(cmd)
                docker_api.reload_config()
            else:
                docker_api.login(username, password, registry=registry, reauth=True)

class PlainAuthentication(dictobj):
    fields = ["username", "password"]

    @property
    def creds(self):
        return self.username, self.password

class KmsAuthentication(dictobj):
    fields = ["username", "password", "role", "region"]

    @property
    def creds(self):
        session = assume_role(self.role)
        password = decrypt_kms(session, self.password, self.region)
        return self.username, password

class S3SlipAuthentication(dictobj):
    fields = ["location", "role"]

    @property
    def creds(self):
        if not hasattr(self, "_store"):
            self._store = None

        if self._store is not None:
            tm, stored = self._store
            if time.time() - tm > 3000:
                self.store = None
            else:
                return stored

        session = assume_role(self.role)
        slip = get_s3_slip(session, self.location)
        self._store = (time.time(), slip.decode('utf-8').split(":", 1))
        return self._store[1]
