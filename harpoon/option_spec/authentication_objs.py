from harpoon.amazon import assume_role, decrypt_kms, get_s3_slip

from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj

from six.moves.urllib.parse import urlparse
import os

class Authentication(dictobj):
     fields = ["registries"]

     def login(self, docker_context, image_name, is_pushing=False, global_docker=False):
         registry = urlparse("https://{0}".format(image_name)).netloc
         if registry in self.registries:
            if is_pushing:
                authenticator = self.registries[registry]['writing']
            else:
                authenticator = self.registries[registry]['reading']

            if authenticator is not NotSpecified:
                username, password = authenticator.creds
                if global_docker:
                    cmd = "docker login -u {0} -p {1} -e {2} {3}".format(username, password, "emailnotneeded@goawaydocker.com", registry)
                    os.system(cmd)
                else:
                    docker_context.login(username, password, registry=registry)

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
        session = assume_role(self.role)
        slip = get_s3_slip(session, self.location)
        return slip.decode('utf-8').split(":", 1)
