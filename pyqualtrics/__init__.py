# -*- coding: utf-8 -*-
#
# This file is part of the pyqualtrics package.
# For copyright and licensing information about this package, see the
# NOTICE.txt and LICENSE.txt files in its top-level directory; they are
# available at https://github.com/Baguage/pyqualtrics
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import csv
import json
import zipfile
from collections import OrderedDict
import collections
from zipfile import BadZipfile

import requests
import os
import sys

from requests.exceptions import ConnectionError, Timeout, TooManyRedirects, HTTPError

__version__ = "0.6.6"

if sys.version_info >= (3, 0):
    # Python 3.5
    STR = (str, )
    from io import StringIO
    from io import BytesIO
else:
    # Python 2.7
    STR = (str, unicode)
    from StringIO import StringIO

if os.path.exists('.env'):
    for line in open(".env"):
        var = line.strip().split('=')
        if len(var) == 2:
            os.environ[var[0]] = var[1]

class Qualtrics(object):
    """
    This is representation of Qualtrics REST API
    """
    # Export formats (API v3)
    CSV_FORMAT = "csv"
    JSON_FORMAT = "json"
    CSV2013_FORMAT = "csv2013"
    XML_FORMAT = "xml"
    SPSS_FORMAT = "spss"

    # Additional options passed to requests.get or request.post
    # For example, to disable SSL certificate validations, set requests_kwargs to {"verify": False"}
    # Can also be used to specify custom certificate and so on
    # http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification
    requests_kwargs = dict()

    def __init__(self, user=None, token=None, api_version="2.5"):
        """
        :param user: The user name. If omitted, value of environment variable QUALTRICS_USER will be used.
        :param token: API token for the user. If omitted, value of environment variable QUALTRICS_TOKEN will be used.
        :param api_version: API version to use (this library has been tested with version 2.5).
        """
        if user is None:
            user = os.environ.get("QUALTRICS_USER", None)
        if user is None:
            raise ValueError("user parameter should be passed to __init__ or environment variable  QUALTRICS_USER should be set")  # noqa
        self.user = user

        if token is None:
            token = os.environ.get("QUALTRICS_TOKEN", None)
        if token is None:
            raise ValueError("token parameter should be passed to __init__ or environment variable QUALTRICS_TOKEN should be set")  # noqa
        self.token = token
        self.default_api_version = api_version
        # Version must be a string, not an integer or float
        assert self.default_api_version, STR
        self.last_error_message = None
        self.last_status_code = None
        self.last_url = None
        self.last_data = None
        self.json_response = None
        self.r = None  # requests.Response object, for debugging purpose
        self.response = None  # For debugging purpose
        self.url = None # For debugging purpose

    def __str__(self):
        return self.user

    def __repr__(self):
        # Used code snippet from stackoverflow
        # http://stackoverflow.com/questions/1436703/difference-between-str-and-repr-in-python
        # Note this will print Qualtrics token - may be dangerous for logging
        return "%s(%r)" % (self.__class__, self.__dict__)

    def request3(self, url, method="post", stream=False, data=None):
        self.last_url = url
        self.last_data = None
        self.r = None
        self.response = None
        self.last_error_message = "Not yet set by request3 function"
        if data is None:
            data = dict()
        data_json = json.dumps(data)
        headers = {
            "X-API-TOKEN": self.token,
            "Content-Type": "application/json"
        }
        try:
            if method == "post":
                self.last_data = data
                r = requests.post(url, data=data_json, headers=headers)
            elif method == "get":
                r = requests.get(url, headers=headers)
            else:
                raise NotImplementedError("method %s is not supported" % method)
        except (ConnectionError, Timeout, TooManyRedirects, HTTPError) as e:
            # http://docs.python-requests.org/en/master/user/quickstart/#errors-and-exceptions
            # ConnectionError: In the event of a network problem (e.g. DNS failure, refused connection, etc) Requests will raise a ConnectionError exception.
            # HTTPError: Response.raise_for_status() will raise an HTTPError if the HTTP request returned an unsuccessful status code.
            # Timeout: If a request times out, a Timeout exception is raised.
            # TooManyRedirects: If a request exceeds the configured number of maximum redirections, a TooManyRedirects exception is raised.
            self.last_error_message = str(e)
            return None
        self.r = r
        self.response = r.text   # Keep this for backward compatibility with previous versions
        try:
            self.json_response = r.json()
        except:
            self.json_response = None
        if r.status_code != 200:
            # HTTP server error: 404, 500 etc
            # Apparently http code 401 Unauthorized is returned when incorrect token is provided
            self.last_error_message = "HTTP Code %s" % r.status_code
            try:
                if "error" in self.json_response["meta"]:
                    self.last_error_message = self.json_response["meta"]["error"]["errorMessage"]
                    return None
            except:
                # Mailformed response from the server
                pass
            return None

        return r

    def CreateResponseExport(self, format, surveyId, lastResponseId=None, startDate=None, endDate=None, limit=None,
                             includedQuestionIds=None, useLabels=None, decimalSeparator=None, seenUnansweredRecode=None,
                             useLocalTime=None):
        """ API v3
        Starts an export for a survey in specified format (csv, csv2013, xml, json, spss)
        https://api.qualtrics.com/docs/csv

        :param format: (required) Export format
        :type format: str
        :param surveyId: (required) ID of the survey for which to export responses
        :type surveyId: str
        :param lastResponseId: Export all responses received after the specified response
        :type lastResponseId: str
        :param startDate: Recorded date range filter (Only exports responses recorded after the specified date.)
        :type startDate: str datetime
        :param endDate: Recorded date range filter (Only exports responses recorded before the specified date.)
        :type endDate: str datetime
        :param limit: Maximum number of responses exported
        :type limit: int
        :param includedQuestionIds: Export only specified questions (JSON array of Question IDs e.g. ["QID1", "QID3", ... , "QID5"]).
                                    Note that Question IDs are not question labels
        :type includedQuestionIds: str list
        :param useLabels: Export question labels instead of IDs and data as Choice Text
        :type useLabels: bool
        :param decimalSeparator: Decimal separator (Possible values are ,(comma) and .(period))
        :type decimalSeparator: str
        :param seenUnansweredRecode: Recode seen but unanswered questions with this value
        :type seenUnansweredRecode: str
        :param useLocalTime: Use local timezone to determine response date values
        :type useLocalTime: bool
        :return: ID of the response export for GetResponseExportProgress/GetResponseExportFile or None if error occurs
        """
        url = "https://survey.qualtrics.com/API/v3/responseexports"
        data = {
            "format": format,
            "surveyId": surveyId
        }
        if lastResponseId is not None:
            data["lastResponseId"] = lastResponseId
        #     "startDate": startDate,
        #     "endDate": endDate,
        if limit is not None:
            data["limit"] = limit
        if isinstance(includedQuestionIds, STR):
            includedQuestionIds = json.loads(includedQuestionIds)
        if includedQuestionIds:
            data["includedQuestionIds"] = includedQuestionIds
        if useLabels is True:
            data["useLabels"] = True
        #     "decimalSeparator": decimalSeparator,
        #     "seenUnansweredRecode": seenUnansweredRecode,
        #     "useLocalTime": useLocalTime,
        # }
        response = self.request3(url, method="post", data=data)
        if response is None:
            return response
        try:
            responseExportId = response.json()["result"]["id"]
        except Exception as e:
            self.last_error_message = "Mailformed response from server: %s" % e
            return None
        self.response = response
        self.last_error_message = None
        return responseExportId

    def GetResponseExportProgress(self, responseExportId):
        """ Retrieve the status of a response export CreateResponseExport
        https://api.qualtrics.com/docs/get-response-export-progress

        :param responseExportId: ID of the response export, resulted by
        :type responseExportId: str
        :return:
        """
        url = "https://survey.qualtrics.com/API/v3/responseexports/%s" % responseExportId
        response = self.request3(url, method="get")
        if response is None:
            # Server or network error
            return "servfail", self.last_error_message
        try:
            status = response.json()["result"]["status"]

            if status == "complete":
                # Return URL to download the data
                data = response.json()["result"]["file"]
            else:
                # Return Percentage
                data = response.json()["result"]["percentComplete"]
            self.last_error_message = None
        except (ValueError, KeyError, TypeError) as e:
            self.last_error_message = "Mailformed server response: %s" % e
            return "servfail", self.last_error_message

        return status, data

    def GetResponseExportFile(self, responseExportId):
        """ Retrieve the response export file after the export is complete
        https://api.qualtrics.com/docs/get-response-export-file
        :param responseExportId: The ID given to you after running your Response Export call or URL return by GetResponseExportProgress
        :type responseExportId: str
        :return: open file, can be read using .read() function or passed to csv library etc
        """
        if "https://" in responseExportId:
            url = responseExportId
        else:
            url = "https://survey.qualtrics.com/API/v3/responseexports/%s/file" % responseExportId
        response = self.request3(url, method="get")
        if response is None:
            return None

        try:
            # Python 3.5
            iofile = BytesIO(response.content)
        except:
            # Python 2.7
            iofile = StringIO(response.content)
        try:
            archive = zipfile.ZipFile(iofile)
            # https://docs.python.org/2/library/zipfile.html#zipfile.ZipFile.namelist
            # Assuming there is only one file in zip archive returned by Qualtrics
            fh = archive.open(archive.namelist()[0], mode="r")

            # Converting binary file stream to text stream, so it can be fed to csv module etc
            # Note this may not work for large csv files that do not fit in memory
            # Not sure how typical is that with Qualtrics surveys, though
            fp = io.TextIOWrapper(fh)
        except BadZipfile as e:
            self.last_error_message = str(e)
            return None
        self.last_error_message = None
        return fp

    def DownloadResponseExportFile(self, responseExportId, filename):
        """ Download the response export file after the export is complete to the local file system
        https://api.qualtrics.com/docs/get-response-export-file
        :param responseExportId: The ID given to you after running your Response Export call or URL return by GetResponseExportProgress
        :type responseExportId: str
        :param filename: where to save zip file returned by Qualtrics
        :type filename: str
        :return: True is success, None if error
        """
        if "https://" in responseExportId:
            url = responseExportId
        else:
            url = "https://survey.qualtrics.com/API/v3/responseexports/%s/file" % responseExportId
        response = self.request3(url, method="get", stream=True)
        if response is None:
            return None
        self.last_error_message = None
        with open(filename, "wb") as fp:
            for chunk in response.iter_content(8192):
                fp.write(chunk)
        return True

    def request(self, Request, Product='RS', post_data=None, post_files=None, **kwargs):
        """ Send GET or POST request to Qualtrics API using v2.x format
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#overview_2.5

        This function also sets self.last_error_message and self.json_response

        :param Request: The name of the API call to be made ("createPanel", "deletePanel" etc).
        :param post_data: Content of POST request. If None, GET request will be sent
        :param post_files: Files to post (for importSurvey API call)
        :param kwargs: Additional parameters for this API Call (LibraryID="abd", PanelID="123")
        :return: None if request failed
        """
        Version = kwargs.pop("Version", self.default_api_version)
        # Version must be a string, not an integer or float
        assert Version, STR

        # Handling for Multi Product API calls
        if self.url:
            # Force URL, for use in unittests.
            url = self.url
        elif Product == 'RS':
            url = "https://survey.qualtrics.com/WRAPI/ControlPanel/api.php"
        elif Product == 'TA':
            url = "https://survey.qualtrics.com/WRAPI/Contacts/api.php"
        else:
            raise NotImplementedError('Please specify a valid product api')

        # Special case for handling embedded data
        ed = kwargs.pop("ED", None)

        # http://stackoverflow.com/questions/38987/how-can-i-merge-two-python-dictionaries-in-a-single-expression
        params = {"User": self.user,
                       "Token": self.token,
                       "Format": "JSON",
                       "Version": Version,
                       "Request": Request,
                       }
        # Python 2 and 3 compatible dictionary merge
        for item in kwargs:
            params[item] = kwargs[item]

        # Format embedded data properly,
        # Example: ED[SubjectID]=CLE10235&ED[Zip]=74534
        if ed is not None:
            for key in ed:
                params["ED[%s]" % key] = ed[key]

        self.json_response = None
        self.last_error_message = "Not yet set by request function"
        self.last_status_code = None
        try:
            if post_data:
                r = requests.post(url,
                                  data=post_data,
                                  params=params,
                                  **self.requests_kwargs)
            elif post_files:
                r = requests.post(url,
                                  files=post_files,
                                  params=params,
                                  **self.requests_kwargs)
            else:
                r = requests.get(
                    url,
                    params=params,
                    **self.requests_kwargs
                )
        except (ConnectionError, Timeout, TooManyRedirects, HTTPError) as e:
            # http://docs.python-requests.org/en/master/user/quickstart/#errors-and-exceptions
            # ConnectionError: In the event of a network problem (e.g. DNS failure, refused connection, etc) Requests will raise a ConnectionError exception.
            # HTTPError: Response.raise_for_status() will raise an HTTPError if the HTTP request returned an unsuccessful status code.
            # Timeout: If a request times out, a Timeout exception is raised.
            # TooManyRedirects: If a request exceeds the configured number of maximum redirections, a TooManyRedirects exception is raised.
            self.last_url = ""
            self.response = None
            self.last_error_message = str(e)
            return None

        self.last_url = r.url
        self.response = r.text
        self.last_status_code = r.status_code
        if r.status_code == 403:
            self.last_error_message = "API Error: HTTP Code %s (Forbidden)" % r.status_code
            return None
        if r.status_code == 401 and Request == "getSurvey":
            # I'm don't know if 401 is returned for requests other than getSurvey
            self.last_error_message = "API Error: HTTP Code %s (Unauthorized)" % r.status_code
            return None

        try:
            if Request == "getLegacyResponseData":
                # Preserve order of responses and fields in each response using OrderedDict
                json_response = json.loads(r.text, object_pairs_hook=collections.OrderedDict)
            else:
                # Don't not use OrderedDict for simplicity.
                json_response = json.loads(r.text)
        except ValueError:
            # If the data being deserialized is not a valid JSON document, a ValueError will be raised.
            self.json_response = None
            if "Format" not in kwargs:
                self.last_error_message = "Unexpected response from Qualtrics: not a JSON document"
                return None
            else:
                # Special case - getSurvey. That request has a custom response format (xml).
                # It does not follow the default response format
                self.last_error_message = None
                return r.text

        self.json_response = json_response
        # Sanity check.
        if (Request == "getLegacyResponseData" or Request == "getPanel" or Request == 
            "getListContacts") and "Meta" not in json_response:
            # Special cases - getLegacyResponseData, getPanel and getListContacts
            # Success
            self.last_error_message = None
            return json_response
        if "Meta" not in json_response:
            # Should never happen
            self.last_error_message = "Unexpected response from Qualtrics: no Meta key in JSON response"
            return None
        if "Status" not in json_response["Meta"]:
            # Should never happen
            self.last_error_message = "Unexpected response from Qualtrics: no Status key in JSON response"
            return None

        if json_response["Meta"]["Status"] == "Success":
            self.last_error_message = None
            return json_response

        # If error happens, it returns JSON object too
        # Error message is in json_response["Meta"]["ErrorMessage"]
        self.last_error_message = json_response["Meta"]["ErrorMessage"]
        return None

    def createPanel(self, LibraryID, Name, **kwargs):
        """ Creates a new Panel in the Qualtrics System and returns the id of the new panel
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#createPanel_2.5

        :param LibraryID:   The library id you want to create the panel in
        :param Name: The name of the new panel
        :return: PanelID of new panel, None if error occurs
        """
        if self.request("createPanel", LibraryID=LibraryID, Name=Name, **kwargs) is None:
            return None
        return self.json_response["Result"]["PanelID"]

    def deletePanel(self, LibraryID, PanelID, **kwargs):
        """ Deletes the panel.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#deletePanel_2.5

        :param LibraryID: The library id the panel is in.
        :param PanelID: The panel id that will be deleted.
        :return: True if deletion was successful, False otherwise
        """
        if self.request("deletePanel", LibraryID=LibraryID, PanelID=PanelID, **kwargs) is None:
            return False
        return True

    def getPanelMemberCount(self, LibraryID, PanelID, **kwargs):
        """ Gets the number of panel members
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getPanelMemberCount_2.5
        :param LibraryID: The library ID where this panel belongs
        :param PanelID: The panel ID
        :param kwargs: Additional parameters (used by unittest)
        :return: The Number of members
        """
        if self.request("getPanelMemberCount", LibraryID=LibraryID, PanelID=PanelID, **kwargs) is None:
            return None
        return int(self.json_response["Result"]["Count"])

    def addRecipient(self, LibraryID, PanelID, FirstName, LastName, Email, ExternalDataRef, Language, ED):
        """ Add a new recipient to a panel
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#addRecipient_2.5

        :param LibraryID: The library the recipient belongs to
        :param PanelID:     The panel to add the recipient
        :param FirstName:   The first name
        :param LastName:    The last name
        :param Email:   The email address
        :param ExternalDataRef:     The external data reference
        :param Language:    The language code
        :param ED:      The embedded data (dictionary)
        :return:    The Recipient ID or None
        """
        if not self.request("addRecipient",
                            LibraryID=LibraryID,
                            PanelID=PanelID,
                            FirstName=FirstName,
                            LastName=LastName,
                            Email=Email,
                            ExternalDataRef=ExternalDataRef,
                            Language=Language,
                            ED=ED):
            return None
        return self.json_response["Result"]["RecipientID"]

    def getRecipient(self, LibraryID, RecipientID):
        """Get a representation of the recipient and their history
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getRecipient_2.5

        :param LibraryID: The library the recipient belongs to
        :param RecipientID: The recipient id of the person's response history you want to retrieve
        """
        if not self.request("getRecipient", LibraryID=LibraryID, RecipientID=RecipientID):
            return None
        return self.json_response["Result"]["Recipient"]

    def removeRecipient(self, LibraryID, PanelID, RecipientID, **kwargs):
        """ Removes the specified panel member recipient from the specified panel.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#removeRecipient_2.5

        :param LibraryID: The library the recipient belongs to
        :param PanelID: The panel to remove the recipient from
        :param RecipientID: The recipient id of the person that will be updated
        :return: True if successful, False otherwise
        """
        if not self.request("removeRecipient", LibraryID=LibraryID, PanelID=PanelID, RecipientID=RecipientID, **kwargs):
            return False
        return True

    def sendSurveyToIndividual(self, **kwargs):
        """ Sends a survey through the Qualtrics mailer to the individual specified.
        Note that request will be put to queue and emails are not sent immediately (although they usually
        delivered in a few seconds after this function is complete)

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#sendSurveyToIndividual_2.5

        Example response (success):
        {u'Meta': {u'Status': u'Success', u'Debug': u''},
        u'Result': {u'DistributionQueueID': u'EMD_e3F0KAIVfzIYw0R', u'EmailDistributionID': u'EMD_e3F0KAIVfzIYw0R', u'Success': True}}

        :param kwargs:
        :return: EmailDistributionID
        """
        if not self.request("sendSurveyToIndividual", **kwargs):
            return None
        return self.json_response["Result"]["EmailDistributionID"]

    def sendSurveyToPanel(self, SurveyID, SendDate, SentFromAddress, FromEmail, FromName, Subject, MessageID, MessageLibraryID, PanelID, PanelLibraryID, LinkType, **kwargs):
        """ Sends a survey through the Qualtrics mailer to the panel specified.
        Note that request will be put to queue and emails are not sent immediately (although they usually
        delivered in a few seconds after this function is complete)

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#sendSurveyToPanel_2.5

        Example response (success):
        {"Meta":{"Status":"Success","Debug":""},
        "Result":{"Success":true,"EmailDistributionID":"EMD_0DQNoLbdDMeGvK5", "DistributionQueueID":"EMD_0DQNoLbdDMeGvK5"}}

        :param LinkType: The type of link that will be sent out.
        Individual (default) - one unique link for each recipient will be generated that can be taken one time.
        Multiple - a unique link is sent out to each recipient that can be taken multiple times.
        Anonymous - the same generic link is sent to all recipients and can be taken multiple times
        :param kwargs:
        :
        :return: EmailDistributionID
        """
        if not self.request("sendSurveyToPanel", 
                            SurveyID=SurveyID, 
                            SendDate=SendDate, 
                            SentFromAddress=SentFromAddress, 
                            FromEmail=FromEmail, 
                            FromName=FromName, 
                            Subject=Subject, 
                            MessageID=MessageID, 
                            MessageLibraryID=MessageLibraryID, 
                            PanelID=PanelID,
                            PanelLibraryID=PanelLibraryID,
                            LinkType=LinkType, 
                             **kwargs):
            return None
        return self.json_response["Result"]["EmailDistributionID"]

    def sendReminder(self, ParentEmailDistributionID, SendDate, SentFromAddress, FromEmail, FromName, Subject, MessageID, LibraryID, **kwargs):
        """ Sends a survey through the Qualtrics mailer to the panel specified.
        Note that request will be put to queue and emails are not sent immediately (although they usually
        delivered in a few seconds after this function is complete)

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#sendReminder_2.5

        Example response (success):
        {u'Meta': {u'Status': u'Success', u'Debug': u''},
        u'Result': {u'DistributionQueueID': u'EMD_e3F0KAIVfzIYw0R', u'EmailDistributionID': u'EMD_e3F0KAIVfzIYw0R', u'Success': True}}

        :param kwargs:
        :return: EmailDistributionID
        """
        if not self.request("sendReminder", 
                            ParentEmailDistributionID=ParentEmailDistributionID,
                            SendDate=SendDate, 
                            SentFromAddress=SentFromAddress, 
                            FromEmail=FromEmail, 
                            FromName=FromName, 
                            Subject=Subject, 
                            MessageID=MessageID, 
                            LibraryID=LibraryID, 
                             **kwargs):
            return None
        return self.json_response["Result"]["EmailDistributionID"]

    def createDistribution(self, SurveyID, PanelID, Description, PanelLibraryID, **kwargs):
        """ Creates a distribution for survey and a panel. No emails will be sent. Distribution Links can be generated
        later to take the survey.

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#createDistribution_2.5

        :param SurveyID:        The parent distribution you are reminding
        :param PanelID:         The panel you want to send to
        :param Description:     A description for this distribution
        :param PanelLibraryID:  The library id for the panel
        :return: The distribution id
        """
        if not self.request("createDistribution",
                            SurveyID=SurveyID,
                            PanelID=PanelID,
                            Description=Description,
                            PanelLibraryID=PanelLibraryID,
                            **kwargs):
            return None
        return self.json_response["Result"]["EmailDistributionID"]

    def getDistributions(self, **kwargs):
        """ Returns the data for the given distribution.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getDistributions_2.5

        Requests for distribution surveys to users are queued and not delivered immediately. Thus
        functions like sendSurveyToIndividual will successfully completed even though no email were sent yet.
        DistributionID returned by those functions can be used to check status of email delivery.

        :param kwargs:
        :return:
        """
        if not self.request("getDistributions", **kwargs):
            return None
        return self.json_response

    def getSurveys(self, **kwargs):
        """
        This request returns a list of all the surveys for the user.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getSurveys_2.5
        :param kwargs: Additional parameters to API call
        :return: ordered dictionary of surveys. {survey_id:metadata}
        :rtype dict:
        """
        response = self.request("getSurveys", **kwargs)
        # print response
        surveys = None
        if response:
            surveys = OrderedDict()
            for survey in response["Result"]["Surveys"]:
                surveys[survey['SurveyID']] = survey
        return surveys

    def getSurvey(self, SurveyID):
        # Good luck dealing with XML
        # Response does not include answers though
        return self.request("getSurvey", SurveyID=SurveyID, Format=None)

    def importSurvey(self, ImportFormat, Name, Activate=None, URL=None, FileContents=None, OwnerID=None, **kwargs):
        """
        Import Survey
        Note if contents of survey file is not correct empty survey will be created and error message will be returned
        If it is a problem, it is up to application to handle this situation.

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#importSurvey_2.5

        :param ImportFormat:    The format of the import: TXT, QSF, DOC, MSQ
        :param Name:    The survey name.
        :param Activate: If FALSE (0) will be created in an Inactive state. If TRUE (1) will be created in an active state.
        :param URL: If present it will import the file from the given URL.
        :param FileContents:
        :param OwnerID:
        :return:
        """
        result = self.request(
            "importSurvey",
             ImportFormat=ImportFormat,
             Name=Name,
             Activate=Activate,
             URL=URL,
             OwnerID=OwnerID,
             post_files={"FileContents": FileContents} if FileContents else None,
             **kwargs
        )
        if result is not None:
            return result["Result"]["SurveyID"]

    def deleteSurvey(self, SurveyID, **kwargs):
        """
        Delete the specified survey
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#deleteSurvey_2.5

        :param SurveyID: ID of the survey
        :param kwargs: Additional parameters for API
        :return:
        """
        if self.request("deleteSurvey", SurveyID=SurveyID) is not None:
            return True
        return False

    def activateSurvey(self, SurveyID, **kwargs):
        """ Activates the specified Survey
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#activateSurvey_2.5
        :param SurveyID: The Survey ID to activate
        :return:
        """
        if self.request("activateSurvey", SurveyID=SurveyID, **kwargs):
            return True
        return False

    def deactivateSurvey(self, SurveyID, **kwargs):
        """ Deactivates the specified Survey
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#deactivateSurvey_2.5
        :param SurveyID: The Survey ID to deactivate
        :return:
        """
        if self.request("deactivateSurvey", SurveyID=SurveyID, **kwargs):
            return True
        return False

    def getLegacyResponseData(
            self,
            SurveyID,
            LastResponseID=None,
            Limit=None,
            ResponseID=None,
            ResponseSetID=None,
            SubgroupID=None,
            StartDate=None,
            EndDate=None,
            Questions=None,
            Labels=None,
            ExportTags=None,
            ExportQuestionIDs=None,
            LocalTime=None,
            UnansweredRecode=None,
            PanelID=None,
            ResponsesInProgress=None,
            LocationData=None,
            **kwargs):
        """ Returns all of the response data for a survey in the original (legacy) data format.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getLegacyResponseData_2.5

        :param SurveyID:    The survey you will be getting the responses for.
        :param kwargs: Additional parameters allowed by getLegacyResponseData API call
        :return:
        """
        return self.request(
            "getLegacyResponseData",
            SurveyID=SurveyID,
            LastResponseID=LastResponseID,
            Limit=Limit,
            ResponseID=ResponseID,
            ResponseSetID=ResponseSetID,
            SubgroupID=SubgroupID,
            StartDate=StartDate,
            EndDate=EndDate,
            Questions=Questions,
            Labels=Labels,
            ExportTags=ExportTags,
            ExportQuestionIDs=ExportQuestionIDs,
            LocalTime=LocalTime,
            UnansweredRecode=UnansweredRecode,
            PanelID=PanelID,
            ResponsesInProgress=ResponsesInProgress,
            LocationData=LocationData,
            **kwargs)

    def getResponse(self, SurveyID, ResponseID, **kwargs):
        """ Get data for a single response ResponseID in SurveyID. SurveyID is required by API
        Refer to https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getLegacyResponseData_2.5 for additional
        information about kwargs

        :param SurveyID: The survey you will be getting the responses for.
        :param ResponseID: The response id of an individual response.
        :param kwargs: Additional arguments (Labels, Questions, ExportQuestionID, ExportTags, LocalTime, etc)
        :return: response as Python dictionary.
        Example:
        {u'Status': u'0', u'StartDate': u'2015-10-23 10:59:12', u'Q1': 2, u'Q2': 1, u'EndDate': u'2015-10-23 10:59:23',
        u'Name': u'Freeborni, Anopheles', u'IPAddress': u'129.74.236.110', u'Q3': 2, u'ExternalDataReference': u'',
        u'Finished': u'1', u'EmailAddress': u'pyqualtrics+2@gmail.com', u'ResponseSet': u'Default Response Set'}
        """
        response = self.getLegacyResponseData(SurveyID=SurveyID, ResponseID=ResponseID, **kwargs)
        # Don't do "if not response:" - because getLegacyResponseData can return empty dict in some cases
        if response is None:
            return None
        if ResponseID not in response:
            # Should never happen
            self.last_error_message = "Qualtrics error: ResponseID %s not in response (probably deleted)" % ResponseID
            return None
        return response[ResponseID]

    def importResponses(self, SurveyID,
                        ResponseSetID=None,
                        FileURL=None,
                        Delimiter=None,
                        Enclosure=None,
                        IgnoreValidation=None,
                        DecimalFormat=None,
                        FileContents=None,
                        **kwargs):
        """ This request imports responses from csv file or URL to the specified survey.
        Refer to https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#importResponses_2.5 for additional info

        :param SurveyID: The ID of the Survey the responses will be connected to.
        :param ResponseSetID: The ID of the response set the responses will be placed in.
        :param FileURL: The location of the CSV file containing the responses to be imported, we only support CSV files from ftp, ftps, http, and https. If you dont specify, it will use php://input from the request body.
        :param Delimiter:   Separate values by this character. Default is , (comma)
        :param Enclosure: Allows a value to contain the delimiter. Default is " (quote)
        :param IgnoreValidation: If set to true (1), we will not validate the responses as we import.
        :param DecimalFormat: Decimals delimiter. Possible values are ,(comma) and .(period)
        :param FileContents: The contents of the file posted using multipart/form-data
        :return:
        """
        if not self.request(
                "importResponses",
                SurveyID=SurveyID,
                ResponseSetID=ResponseSetID,
                FileURL=FileURL,
                Delimiter=Delimiter,
                Enclosure=Enclosure,
                IgnoreValidation=IgnoreValidation,
                DecimalFormat=DecimalFormat,
                post_files={"FileContents": FileContents} if FileContents else None,
                **kwargs):
            return False
        return True

    def importResponsesAsDict(self, SurveyID, responses,
                        ResponseSetID=None,
                        Delimiter=None,
                        Enclosure=None,
                        IgnoreValidation=None,
                        DecimalFormat=None,
                        **kwargs):
        """ Import responses from a python dictionary
        Refer to https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#importResponses_2.5 for additional info

        :param SurveyID:
        :param responses: list of responses. Each response is represented as a dictionary
            [
            {"ResponseID": "R_1234", ...},
            {"ResponseID": "R_1235", "Finished": "1", ...},
            ]
        :param ResponseSetID: The ID of the response set the responses will be placed in.
        :param Delimiter: Separate values by this character. Default is , (comma)
        :param Enclosure: Allows a value to contain the delimiter. Default is " (quote)
        :param IgnoreValidation: If set to true (1), we will not validate the responses as we import.
        :param DecimalFormat: Decimals delimiter. Possible values are ,(comma) and .(period)
        :param kwargs: Additional parameters
        :return:
        """
        assert(isinstance(responses, list))
        if len(responses) < 1:
            return True
        headers = responses[0].keys()
        fp = StringIO()
        dictwriter = csv.DictWriter(fp, fieldnames=headers)
        dictwriter.writeheader()
        dictwriter.writeheader()
        for response in responses:
            dictwriter.writerow(response)

        contents = fp.getvalue()
        return self.importResponses(
            SurveyID=SurveyID,
            ResponseSetID=ResponseSetID,
            Delimiter=Delimiter,
            Enclosure=Enclosure,
            IgnoreValidation=IgnoreValidation,
            DecimalFormat=DecimalFormat,
            FileContents=contents,
            **kwargs)

    def updateResponseEmbeddedData(self, SurveyID, ResponseID, ED, **kwargs):
        """
        Updates the embedded data for a given response.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#updateResponseEmbeddedData_2.5

        :param SurveyID: The survey ID of the response to update.
        :param ResponseID: The response ID for the response to update.
        :param ED: The new embedded data, dictionary
        :param kwargs: Additional arguments (Version, Format etc)
        :return: True or False
        """
        if not self.request(
                "updateResponseEmbeddedData",
                SurveyID=SurveyID,
                ResponseID=ResponseID,
                ED=ED,
                **kwargs):
            return False
        return True

    def getPanels(self, LibraryID):
        """ This request returns all the panels contained in the library

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getPanels_2.5

        :param LibraryID: The id of the library that contains the panels
        :return:
        """
        response = self.request("getPanels", LibraryID=LibraryID)
        if not response:
            return None
        return response["Result"]["Panels"]

    def getPanel(self, LibraryID, PanelID, EmbeddedData=None, LastRecipientID=None, NumberOfRecords=None,
                 ExportLanguage=None, Unsubscribed=None, Subscribed=None, **kwargs):
        """ Gets all the panel members for the given panel
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getPanel_2.5
        :param LibraryID: The library id for this panel
        :param PanelID:     The panel id you want to export
        :param EmbeddedData: A comma separated list of the embedded data keys you want to export. This is only required for a CSV export.
        :param LastRecipientID: The last Recipient ID from a previous API call. Start returning everyone AFTER this Recipient
        :param NumberOfRecords:     The number of panel members to return. If not defined will return all of them
        :param ExportLanguage:  If 1 the language of each panel member will be exported.
        :param Unsubscribed: If 1 only the unsubscribed panel members will be returned
        :param Subscribed:  If 1 then only subscribed panel members will be returned
        :return: list of panel member as dictionaries
        """
        return self.request(
            "getPanel",
            LibraryID=LibraryID,
            PanelID=PanelID,
            EmbeddedData=EmbeddedData,
            LastRecipientID=LastRecipientID,
            NumberOfRecords=NumberOfRecords,
            ExportLanguage=ExportLanguage,
            Unsubscribed=Unsubscribed,
            Subscribed=Subscribed,
            **kwargs
        )

    def importPanel(self, LibraryID, Name, CSV, **kwargs):
        """ Imports a csv file as a new panel (optionally it can append to a previously made panel) into the database
        and returns the panel id.  The csv file can be posted (there is an approximate 8 megabytes limit)  or a url can
        be given to retrieve the file from a remote server.
        The csv file must be comma separated using " for encapsulation.

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#importPanel_2.5

        :param LibraryID:
        :param Name:
        :param CSV: contents of CSV file to be imported
        :return:
        """

        if kwargs.get("ColumnHeaders", None) == "1" or kwargs.get("ColumnHeaders", None) == 1:
            fp = StringIO(CSV)
            headers = next(csv.reader(fp))
            if "Email" in headers and "Email" not in kwargs:
                kwargs["Email"] = headers.index("Email") + 1
            if "FirstName" in headers and "FirstName" not in kwargs:
                kwargs["FirstName"] = headers.index("FirstName") + 1
            if "LastName" in headers and "LastName" not in kwargs:
                kwargs["LastName"] = headers.index("LastName") + 1
            if "ExternalRef" in headers and "ExternalRef" not in kwargs:
                kwargs["ExternalRef"] = headers.index("ExternalRef") + 1
            fp.close()

        result = self.request("importPanel", post_data=CSV, LibraryID=LibraryID, Name=Name, **kwargs)
        if result is not None:
            return result["Result"]["PanelID"]
        return None

    def importContacts(self, LibraryID, Name, CSV, **kwargs):
        """ Asynchronously imports a csv file into your directory
        (optionally it can create a new list or append to an existing list).
         * If the ContactID is specified for the row, it attempts to update the contact; otherwise one is created.
         * The csv file can be posted (there is an approximate 50 megabyte limit) or a url can be given to retrieve the file from a remote server via http or https.
         * The csv file must be comma separated using " for encapsulation. It must also contain headers with appropriately-named columns for Email, FirstName, LastName, ExternalRef, Language, and Unsubscribed.
          * A job id is returned and can be used to check the status of the import using the checkImportContactsStatus API call

        https://survey.qualtrics.com/WRAPI/Contacts/docs.php#importContacts_2.3

        :param LibraryID:
        :param Name:
        :param CSV: contents of CSV file to be imported
        :return:
        """

        if kwargs.get("ColumnHeaders", None) == "1" or kwargs.get("ColumnHeaders", None) == 1:
            fp = StringIO(CSV)
            headers = csv.reader(fp).next()
            if "Email" in headers and "Email" not in kwargs:
                kwargs["Email"] = headers.index("Email") + 1
            if "FirstName" in headers and "FirstName" not in kwargs:
                kwargs["FirstName"] = headers.index("FirstName") + 1
            if "LastName" in headers and "LastName" not in kwargs:
                kwargs["LastName"] = headers.index("LastName") + 1
            if "ExternalRef" in headers and "ExternalRef" not in kwargs:
                kwargs["ExternalRef"] = headers.index("ExternalRef") + 1
            fp.close()

        result = self.request("importContacts", Product="TA", post_data=CSV, LibraryID=LibraryID, Name=Name, **kwargs)
        if result is not None:
            return result["Result"]["ListID"]
        return None

    def importJsonPanel(self, LibraryID, Name, panel, headers=None, **kwargs):
        """ Import JSON document as a new panel. Example document:
        [
        {"Email": "pyqualtrics@gmail.com", "FirstName": "PyQualtrics", "LastName": "Library"},
        {"Email": "pyqualtrics+2@gmail.com", "FirstName": "PyQualtrics2", "LastName": "Library2"}
        ]

        :param LibraryID:
        :param Name:
        :param panel:
        :param kwargs:
        :param headers:
        :return:
        """
        if headers is None:
            headers = ["Email", "FirstName", "LastName", "ExternalRef"]
        fp = StringIO()
        dictwriter = csv.DictWriter(fp, fieldnames=headers)
        dictwriter.writeheader()
        for subject in panel:
            dictwriter.writerow(subject)

        contents = fp.getvalue()
        return self.importPanel(LibraryID=LibraryID,
                                Name=Name,
                                CSV=contents,
                                ColumnHeaders="1",
                                **kwargs
                                )

    def getSingleResponseHTML(self, SurveyID, ResponseID, **kwargs):
        """ Return response in html format (generated by Qualtrics)

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getSingleResponseHTML_2.5

        :param SurveyID:   The response's associated survey ID
        :param ResponseID: The response to get HTML for
        :param kwargs:     Addition parameters
        :return:  html response as a string
        """
        if not self.request("getSingleResponseHTML",
                            SurveyID=SurveyID,
                            ResponseID=ResponseID,
                            **kwargs):
            return None

        return self.json_response["Result"]

    def getAllSubscriptions(self):
        """ Allows a 3rd party to check the status of all their subscriptions.
        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#getAllSubscriptions_2.5

        !!! NOT YET TESTED !!!

        :return:
        """
        return self.request(
            "getAllSubscriptions",
        )

    def subscribe(self, Name, PublicationURL, Topics, Encrypt=None, SharedKey=None, BrandID=None, **kwargs):
        """ Allows a 3rd party client to subscribe to Qualtrics events.
        Topic subscription can be a single event * (Ex: 'threesixty.created') or a wildcard list of events
        using the * (star) notation to denote 'everything'
        (Ex:’threesixty.*’ will subscribe to all 360 events from Qualtrics.)

        !!! NOT YET TESTED !!!

        https://survey.qualtrics.com/WRAPI/ControlPanel/docs.php#subscribe_2.5

        :return:
        """
        result = self.request(
            "subscribe",
            Name=Name,
            PublicationURL=PublicationURL,
            Topics=Topics,
            Encrypt=Encrypt,
            SharedKey=SharedKey,
            BrandID=BrandID,
        )

        return result

    def generate_unique_survey_link(
            self,
            SurveyID,
            LibraryID,
            PanelID,
            DistributionID,
            FirstName,
            LastName,
            Email,
            ExternalDataRef="",
            Language="English",
            EmbeddedData=None
    ):
        """ Generate unique survey link for a person. Based on a response from Qualtrics Support
        :param SurveyID:
        :param LibraryID:
        :param PanelID:
        :param DistributionID:
        :param FirstName:
        :param LastName:
        :param Email:
        :param ExternalDataRef: (optional, defaults to "")
        :param Language: (optional, defaults to "English")
        :param EmbeddedData: (optional)
        :return:
        """
        assert isinstance(EmbeddedData, (dict, type(None)))
        assert isinstance(SurveyID, STR)
        assert isinstance(DistributionID, STR)

        if EmbeddedData is None:
            EmbeddedData = {}
        recipient_id = self.addRecipient(LibraryID, PanelID, FirstName=FirstName, LastName=LastName, Email=Email, ExternalDataRef=ExternalDataRef, Language=Language, ED=EmbeddedData)
        if recipient_id is None:
            # last_error_message is set by addRecipient function
            return None
        if "_" not in SurveyID:
            self.last_error_message = "Invalid SurveyID format (must be SV_xxxxxxxxxx)"
            return None

        if "_" not in DistributionID:
            self.last_error_message = "Invalid DistributionID format (must be EMD_xxxxxxxxxx)"
            return None

        link = DistributionID.split("_")[1] + "_" + SurveyID.split("_")[1] + "_" + recipient_id

        link = "http://new.qualtrics.com/SE?Q_DL=%s" % link

        return link

    def getListContacts(self, LibraryID, ListID, EmbeddedData=None, ContactHistory=None, LastRecipientID=None, NumberOfRecords=None,
                 ExportLanguage=None, Unsubscribed=None, Subscribed=None, **kwargs):
        """ Gets all the list members for the given list

        https://survey.qualtrics.com/WRAPI/Contacts/docs.php#getListContacts_2.3

        :param LibraryID: The library id for this list
        :param ListID:     The list id you want to export
        :param EmbeddedData: A comma separated list of the embedded data keys you want to export. This is only required for a CSV export.
        :param LastRecipientID: The last Recipient ID from a previous API call. Start returning everyone AFTER this Recipient
        :param NumberOfRecords:     The number of list members to return. If not defined will return all of them
        :param ExportLanguage:  If 1 the language of each list member will be exported.
        :param Unsubscribed: If 1 only the unsubscribed list members will be returned
        :param Subscribed:  If 1 then only subscribed list members will be returned
        :return: list of list members as dictionaries
        """
        if not self.request("getListContacts",
                            Product='TA',
                            LibraryID=LibraryID,
                            ListID=ListID,
                            EmbeddedData=EmbeddedData,
                            ContactHistory=ContactHistory,
                            LastRecipientID=LastRecipientID,
                            NumberOfRecords=NumberOfRecords,
                            ExportLanguage=ExportLanguage,
                            Unsubscribed=Unsubscribed,
                            Subscribed=Subscribed,
                            **kwargs):
            print(self.last_error_message)
            return None
        return self.json_response

    def removeContact(self, LibraryID, ListID, RecipientID, **kwargs):
        """ Remove contact from the specified list

        https://survey.qualtrics.com/WRAPI/Contacts/docs.php#removeContact_2.3

        :param LibraryID: The library id for this panel
        :param ListID:     The list id you want to export
        :param RecipientID: The id of the contact who is to be removed
        :return: success or failure
        """
        if not self.request("removeContact",
                            Product='TA',
                            LibraryID=LibraryID,
                            ListID=ListID,
                            RecipientID=RecipientID,
                            **kwargs):
            print(self.last_error_message)
            return None
        return self.json_response

    def truncate_contact_list(self, LibraryID, ListID):
        """ Removes all contacts from list but keeps existing list
        :param LibraryID: The library id for this panel
        :param ListID:     The list id you want to export
        :return success or failure
        """
        list_of_contacts = self.getListContacts(LibraryID=LibraryID, ListID=ListID)
        failures = []
        if list_of_contacts:
            for contact in list_of_contacts:
                RecipientID = contact['RecipientID']
                try:
                    self.removeContact(LibraryID=LibraryID, ListID=ListID, RecipientID=RecipientID)
                except Exception as e:
                    # print e
                    failures.append(RecipientID)
        if failures:
            return True, []
        else:
            return False, failures
