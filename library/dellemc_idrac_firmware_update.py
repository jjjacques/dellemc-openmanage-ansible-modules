#!/usr/bin/python
# _*_ coding: utf-8 _*_

#
# Dell EMC OpenManage Ansible Modules
# Version BETA
# Copyright (C) 2018 Dell Inc.

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# All rights reserved. Dell, EMC, and other trademarks are trademarks of Dell Inc. or its subsidiaries.
# Other trademarks may be trademarks of their respective owners.
#

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: dellemc_idrac_firmware_update
short_description: Firmware update from a repository on a remote network share (CIFS, NFS) or a URL (http, https, ftp)
version_added: "2.3"
description:
    - Update the Firmware by connecting to a network repository (CIFS, NFS, HTTP, HTTPS, FTP) that contains a catalog of available updates
    - Remote network share or URL should contain a valid repository of Update Packages (DUPs) and a catalog file describing the DUPs
    - All applicable updates contained in the repository is applied to the system
    - This feature is only available with iDRAC Enterprise License
options:
  idrac_ip:
    required: True
    description:
      - iDRAC IP Address
    type: 'str'
  idrac_user:
    required: True
    description:
      - iDRAC user name
    type: 'str'
  idrac_pwd:
    required: True
    description:
      - iDRAC user password
    type: 'str'
  idrac_port:
    required: False
    description:
      - iDRAC port
    default: 443
    type: 'int'
  share_name:
    required: True
    description:
      - Network share (CIFS, NFS, HTTP, HTTPS, FTP) containing the Catalog file and Update Packages (DUPs)
    type: 'str'
  share_user:
    required: False
    description:
      - Network share user in the format 'user@domain' or or 'domain\\user' if user is part of a domain else 'user'. This option is mandatory if I(share_name) is a CIFS share
    type: 'str'
    default: None
  share_pwd:
    required: False
    description:
      - Network share user password
    type: 'str'
    default: None
  catalog_file_name:
    required: False
    description:
      - Catalog file name relative to the I(share_name)
    default: 'Catalog.xml'
    type: 'str'
  apply_update:
    required: False
    description: 
      - if C(True), the updatable packages from Catalog XML are staged
      - if C(False), do not Install Updates
    default: True
    type: 'bool'
  reboot:
    required: False
    description:
      - if C(True), reboot server for applying the updates
      - if C(False), updates take effect after the system is rebooted the next time
    default: False
    type: 'bool'
  job_wait:
    required: False
    description:
      - if C(True), will wait for update JOB to get completed
      - if C(False), return immediately after creating the update job in job queue
    default: True
    type: 'bool'
  ignore_cert_warning:
    required: False
    description:
      - Specifies if certificate warnings should be ignored when HTTPS share is used
      - if C(True), certificate warnings are ignored
      - if C(False), certificate warnings are not ignored
    default: True
    type: 'bool'

requirements:
  - "omsdk"
  - "python >= 2.7.5"
author:
  - "Anupam Aloke (@anupamaloke)"

'''

EXAMPLES = '''
---
- name: Update firmware from repository on a CIFS Share
    dellemc_idrac_virtual_drive:
       idrac_ip:   "192.168.1.1"
       idrac_user: "root"
       idrac_pwd:  "calvin"
       share_name: "\\\\192.168.10.10\\share"
       share_user: "user1"
       share_pwd:  "password"
       catalog_file_name:  "Catalog.xml"
       apply_update:   True
       reboot:     False
       job_wait:   True

'''

RETURN = '''
---
# Output the status of an firmware update JOB

    "msg": {
        "ElapsedTimeSinceCompletion": "0",
        "InstanceID": "JID_396919089508",
        "JobStartTime": "NA",
        "JobStatus": "Completed",
        "JobUntilTime": "NA",
        "Message": "Job completed successfully.",
        "MessageArguments": "NA",
        "MessageID": "RED001",
        "Name": "Repository Update",
        "PercentComplete": "100",
        "Status": "Success",
        "file": "http://100.100.28.117/firmware/R730-Backplane-Expander-Repo_1.02_Catalog.xml",
        "retval": true
    }

'''

import re
from ansible.module_utils.dellemc_idrac import iDRACConnection
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves.urllib.parse import urlparse

try:
    from omsdk.sdkcreds import UserCredentials
    from omsdk.sdkfile import FileOnShare
    HAS_OMSDK = True
except ImportError:
    HAS_OMSDK = False


def update_fw_from_url(idrac, share_name, share_user, share_pwd,
                       catalog_file_name, apply_update=True,
                       reboot=False, job_wait=True,
                       ignore_cert_warning=True):
    """
    Update firmware from a ftp/http/https URL

    :param share_name: ftp/http/https url for downloading the catalog file and DUPs
    :type share_name: ``str``

    :param share_user: user name for the URL
    :type share_user: ``str``

    :param share_pwd: password for the URL
    :type share_pwd: ``str``

    :param catalog_file_name: Name of the Catalog file on the repository
    :type catalog_file_name: ``str``

    :param apply_update: If apply_update is set to True, the updatable packages from Catalog XML are staged. If it is set to False, no updates are applied.
    :type apply_update: ``bool``

    :param reboot: True if the server needs to be rebooted during the update process. False if the updates take effect after the server is rebooted the next time.
    :type reboot: ``bool``

    :param job_wait: True if need to wait for firmware job to be completed. False if need to return immediately after staging the job in LC queue
    :type job_wait: ``bool``

    :returns: A dict containing the return value from the Update Job
    :rtype: ``dict``
    """

    msg = ""

    # IPv4 address with an optional port number, for e.g. 192.168.10.20:80
    ipv4_re = re.compile(r'(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}(?=$|(?::(\d{2,5})))')

    # URL scheme
    schemes = ["ftp", "http", "https"]

    # Validate URL 
    p = urlparse(share_name)
    if not p:
        msg = "Invalid url: {}".format(share_name)
    else:
        path = p.path
        if p.scheme not in schemes:
            error_str = "URL scheme must be one of " + str(schemes)
            msg = "Invalid url: {}. {}".format(share_name, error_str)
        elif not (p.netloc and re.match(ipv4_re, p.netloc)):
            error_str = "URL netloc must be a valid IPv4 or IPv6 address."
            msg = "Invalid url: {}. {}".format(share_name, error_str)
        else:
            if not p.path:
                # if path is empty (for e.g. in "http://192.168.10.10"), then
                # use "/" as path
                path += "/"

            msg = idrac.update_mgr.update_from_repo_url(
                         ipaddress=p.netloc, share_type=p.scheme,
                         share_name=path, share_user=share_user,
                         share_pwd=share_pwd, catalog_file=catalog_file_name,
                         apply_update=apply_update, reboot_needed=reboot,
                         job_wait=job_wait)

    return msg

def update_fw_from_nw_share(idrac, share_name, share_user, share_pwd,
        catalog_file_name, apply_update=True, reboot=False, job_wait=True):
    """
    Update firmware from a repository on a remote network share (CIFS, NFS) 

    :param idrac: iDRAC connection object
    :type idrac: iDRAC connection object

    :param share_name: CIFS or NFS network share
    :type share_name: ``str``

    :param share_user: username for the remote network share
    :type share_user: ``str``

    :param share_pwd: password for the remote network share
    :type share_pwd: ``str``

    :param catalog_file_name: Name of Catalog file on the repository
    :type catalog_file_name: ``str``

    :param apply_update: Apply update
    :type apply_update: ``bool``

    :param reboot: Reboot system
    :type reboot: ``bool``

    :param job_wait: Wait for JOB to be completed
    :type job_wait: ``bool``

    :returns: A dict containing the return value for the Update Job 
    :rtype: ``dict``
    """

    nw_repo = FileOnShare(remote=share_name, isFolder=True)
    nw_repo.addcreds(UserCredentials(share_user, share_pwd))
    catalog_path = nw_repo.new_file(catalog_file_name)

    msg = idrac.update_mgr.update_from_repo(catalog_path=catalog_path,
                                            apply_update=apply_update,
                                            reboot_needed=reboot,
                                            job_wait=job_wait)

    return msg

def update_fw_from_repo(idrac, module):
    """
    Update firmware from a repository (CIFS, NFS, HTTP, HTTPS, FTP)

    :param idrac: iDRAC handle
    :type idrac: ``iDRAC Connection Object``

    :param module: Ansible module
    :type module: ``class AnsibleModule``

    :returns: A tuple containing a msg dict and error flag
    :rtype: ``tuple``
    """

    msg = {}
    msg['changed'] = False
    msg['failed'] = False
    msg['msg'] = {}
    err = False

    try:
        share_name = module.params.get('share_name')
        share_user = module.params.get('share_user')
        share_pwd = module.params.get('share_pwd')
        catalog_file_name = module.params.get('catalog_file_name')
        apply_update = module.params.get('apply_update')
        reboot = module.params.get('reboot')
        job_wait = module.params.get('job_wait')
        ignore_cert_warning = module.params.get('ignore_cert_warning')

        # check if valid catalog file
        if not catalog_file_name.lower().endswith('.xml'):
            module.fail_json(msg="Invalid catalog file: {}. Must end with \'.xml\' or \'.XML\' extension".format(catalog_file_name))

        # Temporary Fix for iDRAC firmware version < 2.50.50.50
        if any(gen in idrac.ServerGeneration for gen in ['12', '13']):
            idrac.use_redfish = False

        # check if HTTP/HTTPS share
        if share_name.lower().startswith(('http://', 'https://', 'ftp://')): 

            # Update from http/https/ftp repo is currently supported using
            # only WS-Man
            idrac.use_redfish = False
            msg['msg'] = update_fw_from_url(idrac, share_name, share_user,
                                            share_pwd, catalog_file_name,
                                            apply_update, reboot, job_wait,
                                            ignore_cert_warning)
        else:
            # local mount point is required for SCP based firmware update
            # using Redfish
            if idrac.use_redfish and (not module.params.get('share_mnt')):
                module.fail_json(msg="Error: \'share_mnt\' is a mandatory argument for Redfish based firmware update using Server Configuration Profile (SCP)")

            msg['msg'] = update_fw_from_nw_share(idrac, share_name, share_user,
                                                 share_pwd, catalog_file_name,
                                                 apply_update, reboot, job_wait)

        if "Status" in msg['msg']:
            if msg['msg']['Status'] == "Success":
                msg['changed'] = True
            else:
                msg['failed'] = True
        else:
            msg['failed'] = True

    except Exception as e:
        err = True
        msg['msg'] = "Error: %s" % str(e)
        msg['failed'] = True

    return msg, err

# Main
def main():

    module = AnsibleModule(
        argument_spec=dict(

            # iDRAC handle
            idrac=dict(required=False, type='dict'),

            # iDRAC Credentials
            idrac_ip=dict(required=True, type='str'),
            idrac_user=dict(required=True, type='str'),
            idrac_pwd=dict(required=True, type='str', no_log=True),
            idrac_port=dict(required=False, default=443, type='int'),

            # Network File Share
            share_name=dict(required=True, type='str'),
            share_user=dict(required=False, type='str', default=None),
            share_pwd=dict(required=False, type='str', default=None, no_log=True),
            share_mnt=dict(required=False, type='path', default=None),

            # Firmware update parameters
            catalog_file_name=dict(required=False, default='Catalog.xml', type='str'),
            apply_update=dict(required=False, default=True, type='bool'),
            reboot=dict(required=False, default=False, type='bool'),
            job_wait=dict(required=False, default=True, type='bool'),
            ignore_cert_warning=dict(required=False, default=True, type='bool')
        ),

        supports_check_mode=False)

    if not HAS_OMSDK:
        module.fail_json(msg="Dell EMC OpenManage Python SDK required for this module")

    # Connect to iDRAC
    idrac_conn = iDRACConnection(module)
    idrac = idrac_conn.connect()

    msg, err = update_fw_from_repo(idrac, module)

    # Disconnect from iDRAC
    idrac_conn.disconnect()

    if err:
        module.fail_json(**msg)
    module.exit_json(**msg)

if __name__ == '__main__':
    main()