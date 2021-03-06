# Copyright 2017-2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may
# not use this file except in compliance with the License. A copy of the License is located at
#
#        http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for
# the specific language governing permissions and limitations under the License.
import json
import sys
import unittest
from os.path import join, dirname, realpath
from typing import TypedDict, List

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock
import botocore

# https://github.com/awslabs/aws-config-rdk/issues/245
from botocore.exceptions import ClientError

##############
# Parameters #
##############

# Define the default resource to report to Config Rules
DEFAULT_RESOURCE_TYPE = 'AWS::::Account'

#############
# Main Code #
#############

CONFIG_CLIENT_MOCK = MagicMock()
STS_CLIENT_MOCK = MagicMock()


class Boto3Mock():
    @staticmethod
    def client(client_name, *args, **kwargs):
        if client_name == 'config':
            return CONFIG_CLIENT_MOCK
        if client_name == 'sts':
            return STS_CLIENT_MOCK
        raise Exception("Attempting to create an unknown client")


sys.modules['boto3'] = Boto3Mock()

RULE = __import__('NonDefaultMetadataServer')


class Route(TypedDict):
    destinationCidrBlock: str
    gatewayId: str
    state: str
    origin: str


class RouteTableConfig(TypedDict):
    routeTableId: str
    routes: List[Route]


class RouteTableConfigItem(TypedDict):
    resourceId: str
    configuration: RouteTableConfig

class RouteTableConfigEvent(TypedDict):
    configurationItem: RouteTableConfigItem


class ComplianceTest(unittest.TestCase):
    rule_parameters = '{"routes": ["169.254.169.254/32"]}'

    #
    # {
    #             "destinationCidrBlock": "169.254.169.254/32",
    #             "gatewayId": "igw-a5f227c1",
    #             "state": "active",
    #             "origin": "CreateRoute"
    #         }

    route_table_event: RouteTableConfigEvent

    def setUp(self):
        RULE.ASSUME_ROLE_MODE = False
        self.resp_expected = []

        with open(join(dirname(realpath(__file__)), "event.json")) as f:
            self.route_table_event = json.load(f)

    def test_compliant_with_imds_route_update(self):
        response = RULE.lambda_handler(
            build_lambda_configurationchange_event(json.dumps(self.route_table_event), self.rule_parameters), {})
        expected_response = [build_expected_response('COMPLIANT', 'some-resource-id', 'AWS::EC2::RouteTable')]
        assert_successful_evaluation(self, response, expected_response)

    def test_non_compliant_with_imds_route_update(self):
        bad_route = Route(
            destinationCidrBlock="169.254.169.254/32",
            gatewayId="gatewayid",
            origin="CreateRoute",
            state="active"
        )
        self.route_table_event['configurationItem']['configuration']['routes'].append(bad_route)

        change_event = build_lambda_configurationchange_event(json.dumps(self.route_table_event), self.rule_parameters)
        response = RULE.lambda_handler(change_event, {})

        expected_response = [build_expected_response('NON_COMPLIANT', 'some-resource-id', 'AWS::EC2::RouteTable')]
        assert_successful_evaluation(self, response, expected_response)

    def test_compliant_with_ipv6_only_route_update(self):
        bad_route = Route(
            destinationCidrBlock="2001:db8:a::00/64",
            gatewayId="gatewayid",
            origin="CreateRoute",
            state="active"
        )
        self.route_table_event['configurationItem']['configuration']['routes'] = [bad_route]

        change_event = build_lambda_configurationchange_event(json.dumps(self.route_table_event), self.rule_parameters)
        response = RULE.lambda_handler(change_event, {})

        expected_response = [build_expected_response('COMPLIANT', 'some-resource-id', 'AWS::EC2::RouteTable')]
        assert_successful_evaluation(self, response, expected_response)

####################
# Helper Functions #
####################

def build_lambda_configurationchange_event(invoking_event, rule_parameters=None):
    event_to_return = {
        'configRuleName': 'NonDefaultMetadataServer',
        'executionRoleArn': 'roleArn',
        'eventLeftScope': False,
        'invokingEvent': invoking_event,
        'accountId': '123456789012',
        'configRuleArn': 'arn:aws:config:us-east-1:123456789012:config-rule/config-rule-8fngan',
        'resultToken': 'token'
    }
    if rule_parameters:
        event_to_return['ruleParameters'] = rule_parameters
    return event_to_return


def build_lambda_scheduled_event(rule_parameters=None):
    invoking_event = '{"messageType":"ScheduledNotification","notificationCreationTime":"2017-12-23T22:11:18.158Z"}'
    event_to_return = {
        'configRuleName': 'NonDefaultMetadataServer',
        'executionRoleArn': 'roleArn',
        'eventLeftScope': False,
        'invokingEvent': invoking_event,
        'accountId': '123456789012',
        'configRuleArn': 'arn:aws:config:us-east-1:123456789012:config-rule/config-rule-8fngan',
        'resultToken': 'token'
    }
    if rule_parameters:
        event_to_return['ruleParameters'] = rule_parameters
    return event_to_return


def build_expected_response(compliance_type, compliance_resource_id, compliance_resource_type=DEFAULT_RESOURCE_TYPE,
                            annotation=None):
    if not annotation:
        return {
            'ComplianceType': compliance_type,
            'ComplianceResourceId': compliance_resource_id,
            'ComplianceResourceType': compliance_resource_type
        }
    return {
        'ComplianceType': compliance_type,
        'ComplianceResourceId': compliance_resource_id,
        'ComplianceResourceType': compliance_resource_type,
        'Annotation': annotation
    }


def assert_successful_evaluation(test_class, response, resp_expected, evaluations_count=1):
    if isinstance(response, dict):
        test_class.assertEquals(resp_expected['ComplianceResourceType'], response['ComplianceResourceType'])
        test_class.assertEquals(resp_expected['ComplianceResourceId'], response['ComplianceResourceId'])
        test_class.assertEquals(resp_expected['ComplianceType'], response['ComplianceType'])
        test_class.assertTrue(response['OrderingTimestamp'])
        if 'Annotation' in resp_expected or 'Annotation' in response:
            test_class.assertEquals(resp_expected['Annotation'], response['Annotation'])
    elif isinstance(response, list):
        test_class.assertEquals(evaluations_count, len(response))
        for i, response_expected in enumerate(resp_expected):
            test_class.assertEquals(response_expected['ComplianceResourceType'], response[i]['ComplianceResourceType'])
            test_class.assertEquals(response_expected['ComplianceResourceId'], response[i]['ComplianceResourceId'])
            test_class.assertEquals(response_expected['ComplianceType'], response[i]['ComplianceType'])
            test_class.assertTrue(response[i]['OrderingTimestamp'])
            if 'Annotation' in response_expected or 'Annotation' in response[i]:
                test_class.assertEquals(response_expected['Annotation'], response[i]['Annotation'])


def assert_customer_error_response(test_class, response, customer_error_code=None, customer_error_message=None):
    if customer_error_code:
        test_class.assertEqual(customer_error_code, response['customerErrorCode'])
    if customer_error_message:
        test_class.assertEqual(customer_error_message, response['customerErrorMessage'])
    test_class.assertTrue(response['customerErrorCode'])
    test_class.assertTrue(response['customerErrorMessage'])
    if "internalErrorMessage" in response:
        test_class.assertTrue(response['internalErrorMessage'])
    if "internalErrorDetails" in response:
        test_class.assertTrue(response['internalErrorDetails'])


def sts_mock():
    assume_role_response = {
        "Credentials": {
            "AccessKeyId": "string",
            "SecretAccessKey": "string",
            "SessionToken": "string"}}
    STS_CLIENT_MOCK.reset_mock(return_value=True)
    STS_CLIENT_MOCK.assume_role = MagicMock(return_value=assume_role_response)


##################
# Common Testing #
##################

class TestStsErrors(unittest.TestCase):

    def test_sts_unknown_error(self):
        RULE.ASSUME_ROLE_MODE = True
        RULE.evaluate_parameters = MagicMock(return_value=True)
        STS_CLIENT_MOCK.assume_role = MagicMock(side_effect=botocore.exceptions.ClientError(
            {'Error': {'Code': 'unknown-code', 'Message': 'unknown-message'}}, 'operation'))
        response = RULE.lambda_handler(build_lambda_configurationchange_event('{}'), {})
        assert_customer_error_response(
            self, response, 'InternalError', 'InternalError')

    def test_sts_access_denied(self):
        RULE.ASSUME_ROLE_MODE = True
        RULE.evaluate_parameters = MagicMock(return_value=True)
        STS_CLIENT_MOCK.assume_role = MagicMock(side_effect=botocore.exceptions.ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'access-denied'}}, 'operation'))
        response = RULE.lambda_handler(build_lambda_configurationchange_event('{}'), {})
        assert_customer_error_response(
            self, response, 'AccessDenied', 'AWS Config does not have permission to assume the IAM role.')
