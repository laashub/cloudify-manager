#########
# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from os.path import join

EXTRA_INFO = 'extra_info'
STATUS_REPORTER = 'status-reporter'
STATUS_REPORTER_PATH = join('/opt', STATUS_REPORTER)
STATUS_REPORTER_CONFIG_KEY = 'extra_config'
CONFIGURATION_PATH = join(STATUS_REPORTER_PATH,
                          'status_reporter_configuration.yaml')

INTERNAL_REST_PORT = 53333
