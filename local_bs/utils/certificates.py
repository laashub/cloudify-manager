import json
import socket
from os.path import isfile, join
from contextlib import contextmanager

from .common import sudo, remove, chown, copy
from .files import write_to_file, write_to_tempfile

from ..config import config
from ..logger import get_logger
from .. import constants as const

from ..components.service_names import NGINX

logger = get_logger('Certificates')


def _format_ips(ips):
    altnames = set(ips)

    # Ensure we trust localhost
    altnames.add('127.0.0.1')
    altnames.add('localhost')

    subject_altdns = [
        'DNS:{name}'.format(name=name)
        for name in altnames
    ]
    subject_altips = []
    for name in altnames:
        ip_address = False
        try:
            socket.inet_pton(socket.AF_INET, name)
            ip_address = True
        except socket.error:
            # Not IPv4
            pass
        try:
            socket.inet_pton(socket.AF_INET6, name)
            ip_address = True
        except socket.error:
            # Not IPv6
            pass
        if ip_address:
            subject_altips.append('IP:{name}'.format(name=name))

    cert_metadata = ','.join([
        ','.join(subject_altdns),
        ','.join(subject_altips),
    ])
    return cert_metadata


def store_cert_metadata(internal_rest_host, networks=None):
    metadata = load_cert_metadata()
    metadata['internal_rest_host'] = internal_rest_host
    if networks is not None:
        metadata['networks'] = networks
    write_to_file(metadata, const.CERT_METADATA_FILE_PATH, json_dump=True)
    chown(
        const.CLOUDIFY_USER,
        const.CLOUDIFY_GROUP,
        const.CERT_METADATA_FILE_PATH
    )


def load_cert_metadata():
    try:
        with open(const.CERT_METADATA_FILE_PATH) as f:
            return json.load(f)
    except IOError:
        return {}


CSR_CONFIG_TEMPLATE = """
[req]
distinguished_name = req_distinguished_name
req_extensions = server_req_extensions
[ server_req_extensions ]
subjectAltName={metadata}
[ req_distinguished_name ]
commonName = _common_name # ignored, _default is used instead
commonName_default = {cn}
"""


@contextmanager
def _csr_config(cn, metadata):
    """Prepare a config file for creating a ssl CSR.

    :param cn: the subject commonName
    :param metadata: string to use as the subjectAltName, should be formatted
                     like "IP:1.2.3.4,DNS:www.com"
    """
    csr_config = CSR_CONFIG_TEMPLATE.format(cn=cn, metadata=metadata)
    temp_config_path = write_to_tempfile(csr_config)

    try:
        yield temp_config_path
    finally:
        remove(temp_config_path)


def _generate_ssl_certificate(ips,
                              cn,
                              cert_path,
                              key_path,
                              sign_cert=const.INTERNAL_CA_CERT_PATH,
                              sign_key=const.INTERNAL_CA_KEY_PATH):
    """Generate a public SSL certificate and a private SSL key

    :param ips: the ips (or names) to be used for subjectAltNames
    :type ips: List[str]
    :param cn: the subject commonName for the new certificate
    :type cn: str
    :param cert_path: path to save the new certificate to
    :type cert_path: str
    :param key_path: path to save the key for the new certificate to
    :type key_path: str
    :param sign_cert: path to the signing cert (internal CA by default)
    :type sign_cert: str
    :param sign_key: path to the signing cert's key (internal CA by default)
    :type sign_key: str
    :return: The path to the cert and key files on the manager
    """
    # Remove duplicates from ips
    cert_metadata = _format_ips(ips)
    logger.debug('Using certificate metadata: {0}'.format(cert_metadata))

    csr_path = '{0}.csr'.format(cert_path)

    with _csr_config(cn, cert_metadata) as conf_path:
        sudo([
            'openssl', 'req',
            '-newkey', 'rsa:2048',
            '-nodes',
            '-batch',
            '-config', conf_path,
            '-out', csr_path,
            '-keyout', key_path,
        ])
        sudo([
            'openssl', 'x509',
            '-days', '3650',
            '-req', '-in', csr_path,
            '-CA', sign_cert,
            '-CAkey', sign_key,
            '-out', cert_path,
            '-CAcreateserial',
            '-extensions', 'server_req_extensions',
            '-extfile', conf_path
        ])
        remove(csr_path)

    logger.info('Generated SSL certificate: {0} and key: {1}'.format(
        cert_path, key_path
    ))
    return cert_path, key_path


def generate_internal_ssl_cert(ips, name):
    return _generate_ssl_certificate(
        ips,
        name,
        const.INTERNAL_CERT_PATH,
        const.INTERNAL_KEY_PATH
    )


def deploy_or_generate_external_ssl_cert(ips, cn, cert_path, key_path):
    if isfile(cert_path) and isfile(key_path):
        copy(cert_path, const.EXTERNAL_CERT_PATH)
        copy(key_path, const.EXTERNAL_KEY_PATH)

        logger.info(
            'Deployed user-provided SSL certificate `{0}` and SSL private '
            'key `{1}`'.format(
                const.EXTERNAL_CERT_FILENAME,
                const.EXTERNAL_KEY_FILENAME
            )
        )
        return const.EXTERNAL_CERT_PATH, const.EXTERNAL_KEY_PATH
    else:
        logger.info(
            'Generating SSL certificate `{0}` and SSL private '
            'key `{1}`'.format(
                const.EXTERNAL_CERT_FILENAME,
                const.EXTERNAL_KEY_FILENAME
            )
        )

        return _generate_ssl_certificate(
            ips,
            cn,
            const.EXTERNAL_CERT_PATH,
            const.EXTERNAL_KEY_PATH
        )


def generate_ca_cert():
    sudo([
        'openssl', 'req',
        '-x509',
        '-nodes',
        '-newkey', 'rsa:2048',
        '-days', '3650',
        '-batch',
        '-out', const.INTERNAL_CA_CERT_PATH,
        '-keyout', const.INTERNAL_CA_KEY_PATH
    ])
    # PKCS12 file required for riemann due to JVM
    # While we don't really want the private key in there, not having it
    # causes failures
    # The password is also a bit pointless here since it's in the same place
    # as a readable copy of the certificate and if this path can be written to
    # maliciously then all is lost already.
    pkcs12_path = join(
        const.SSL_CERTS_TARGET_DIR,
        const.INTERNAL_PKCS12_FILENAME
    )
    sudo([
        'openssl', 'pkcs12', '-export',
        '-out', pkcs12_path,
        '-in', const.INTERNAL_CA_CERT_PATH,
        '-inkey', const.INTERNAL_CA_KEY_PATH,
        '-password', 'pass:cloudify',
    ])
