#!/usr/bin/env python
'''
ansible module for copying AWS AMIs
'''
# vim: expandtab:tabstop=4:shiftwidth=4
#
#   AWS AMI ansible module
#
#
#   Copyright 2016 Red Hat Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# Jenkins environment doesn't have all the required libraries
# pylint: disable=import-error
import boto3
# Ansible modules need this wildcard import
# pylint: disable=unused-wildcard-import, wildcard-import, redefined-builtin
from ansible.module_utils.basic import *


class AwsAmi(object):
    ''' AWS AMI class '''
    def __init__(self):
        self.module = None
        self.ec2_client = None

    def get_kms_alias_arn(self, alias):
        ''' return IAM KMS arn from provided alias '''

        kms_client = boto3.client('kms')
        aliases = kms_client.list_aliases()['Aliases']
        kms_arns = [x['AliasArn'] for x in aliases if x['AliasName'] == alias]

        if kms_arns:
            return kms_arns[0]

        msg = "Did not find key with alias name: {}".format(alias)
        self.module.exit_json(failed=True, msg=msg)

    def ami_already_exists(self):
        ''' check whether AMI with same name already exists '''
        ami_name = self.module.params['name']
        name_filter = [{'Name': 'name',
                        'Values': [ami_name]
                       }]
        response = self.ec2_client.describe_images(Filters=name_filter)

        # if no results, then no AMI by that name
        if len(response['Images']) == 0:
            return False
        else:
            return True

    def wait_for_ami_available(self, ami_id):
        ''' spin waiting for AMI to enter state 'available' '''

        while True:
            time.sleep(30)
            response = self.ec2_client.describe_images(ImageIds=[ami_id])
            if len(response['Images']) == 1 \
               and response['Images'][0]['State'] == 'available':
                return response['Images'][0]

    def main(self):
        ''' module entrypoint '''

        self.module = AnsibleModule(
            argument_spec=dict(
                state=dict(default='list', choices=['list', 'present'], type='str'),
                ami_id=dict(default=None, required=True, type='str'),
                name=dict(default=None, type='str'),
                region=dict(default=None, required=True, type='str'),
                encrypt=dict(default=False),
                kms_arn=dict(default='', type='str'),
                kms_alias=dict(default=None, type='str'),
                aws_access_key=dict(default=None, type='str'),
                aws_secret_key=dict(default=None, type='str'),
            ),
            mutually_exclusive=[['kms_arn', 'kms_alias']],
            #supports_check_mode=True
        )

        state = self.module.params['state']
        ami_id = self.module.params['ami_id']
        aws_access_key = self.module.params['aws_access_key']
        aws_secret_key = self.module.params['aws_secret_key']
        if aws_access_key and aws_secret_key:
            boto3.setup_default_session(aws_access_key_id=aws_access_key,
                                        aws_secret_access_key=aws_secret_key,
                                        region_name=self.module.params['region'])
        else:
            boto3.setup_default_session(region_name=self.module.params['region'])

        self.ec2_client = boto3.client('ec2')

        if state == 'list':
            if ami_id != None:
                ami = self.ec2_client.describe_images(ImageIds=[ami_id])['Images'][0]
                self.module.exit_json(changed=False, results=ami,
                                      state="list")

        if state == 'present':
            # create request to make an AMI copy
            region = self.module.params['region']
            ami_name = self.module.params['name']
            encrypt = self.module.params['encrypt']
            kms_arn = self.module.params['kms_arn']
            kms_alias = self.module.params['kms_alias']

            if not ami_name:
                self.module.exit_json(failed=True, changed=False,
                                      msg="No AMI name provided")
            if self.ami_already_exists():
                self.module.exit_json(changed=False, msg="AMI already exists")

            if kms_alias:
                kms_arn = self.get_kms_alias_arn(kms_alias)

            response = self.ec2_client.copy_image(SourceRegion=region,
                                                  SourceImageId=ami_id,
                                                  Name=ami_name,
                                                  Encrypted=encrypt,
                                                  KmsKeyId=kms_arn)

            if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                self.module.exit_json(failed=True, changed=True,
                                      results=response)
            else:
                current_stats = self.wait_for_ami_available(response['ImageId'])
                self.module.exit_json(changed=True, results=current_stats)

        self.module.exit_json(failed=True,
                              changed=False,
                              results='Unknown state passed. %s' % state,
                              state="unknown")

#This is not a module, but pylint thinks it is.  This is a command.
#pylint: disable=invalid-name
if __name__ == '__main__':
    AwsAmi().main()
