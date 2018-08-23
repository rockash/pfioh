"""
Handle Swift File Storage Option
"""

import base64
import datetime
import zipfile
import os
import configparser
from   pfioh                       import StoreHandler
from   pfioh                       import base64_process, zip_process, zipdir
from   keystoneauth1.identity      import v3
from   keystoneauth1               import session
from   swiftclient                 import client as swift_client
import pprint

pp = pprint.PrettyPrinter(indent=4)

try:
    from ._colors import Colors
except:
    from _colors import Colors

class SwiftStore(StoreHandler):

    swiftConnection = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.qprint('SwiftStore initialized')
        

    def _getScopedSession(self, osAuthUrl, username, password, osProjectDomain, osProjectName):
        """
        Uses keystone authentication to create and return a scoped session
        """

        passwordAuth  = v3.Password(auth_url=osAuthUrl,
                            user_domain_name='default',
                            username=username, password=password,
                            project_domain_name=osProjectDomain,
                            project_name=osProjectName,
                            unscoped=False)

        scopedSession = session.Session(auth= passwordAuth)
        return scopedSession


    def _initiateSwiftConnection(self, **kwargs):
        """
        Initiates a Swift connection and returns a Swift connection object
        Swift credentials should be stored as a cfg file at /etc/swift 
        """

        str_configPath = '/etc/swift/swift-credentials.cfg'

        for k,v in kwargs:
            if k == 'configPath': str_configPath= v

        config = configparser.ConfigParser()
        try:
            f = open(str_configPath, 'r')
            config.readfp(f)
        finally:
            f.close()
        
        str_osAuthUrl           = config['AUTHORIZATION']['osAuthUrl']
        str_username            = config['AUTHORIZATION']['username']
        str_password            = config['AUTHORIZATION']['password']
        str_osProjectDomain     = config['PROJECT']['osProjectDomain']
        str_osProjectName       = config['PROJECT']['osProjectName']
        
        scopedSession        = self._getScopedSession(str_osAuthUrl, str_username, str_password, str_osProjectDomain, str_osProjectName)
        swiftConnection = swift_client.Connection(session=scopedSession)
        return swiftConnection    

    def _putContainer(self, str_key):
        """
        Creates a container with the name as the key
        """

        self.swiftConnection.put_container(str_key)
        self.qprint('Swift object container created successfully for key %s'%str_key)
        

    def _putObject(self, str_containerName, str_key, str_value):
        """
        Creates an object with the given key and value and puts the object in the specified container
        """

        self.swiftConnection.put_object(str_containerName, str_key , contents=str_value.read(), content_type='text/plain')
        self.qprint('Object added into Swift container: %s' %str_containerName)


    def _downloadObject(self, str_key, b_delete):
        """
        Downloads the specified key in the specified container
        Deletes the object after returning if specified
        """
        try:
            str_containerName = str_key
            str_key = os.path.join('output','data')
            downloadResultsGenerator = self.swiftConnection.download(str_containerName, [str_key], {'out_file': '/tmp/incomingData.zip'})
            if b_delete:
                self.swiftConnection.delete_object(str_containerName, str_key)
                print('Deleted object with key %s' %str_key)
            downloadResults = next(downloadResultsGenerator)
            if downloadResults["success"]:
                print("Download successful")
            else:
                print("Download unsuccessful")
                pp.pprint(downloadResults)
        except Exception as exp:
            print(exp)


    def zipUpContent(self, str_fileContent, str_clientFile):
        """
        Zips up the file content byte stream, reads from archive and returns zipped content
        """

        str_fileName = str_clientFile.split('/')[-1]

        zipfileObj = zipfile.ZipFile('ziparchive.zip', 'w' ,compression= zipfile.ZIP_DEFLATED)
        zipfileObj.writestr(str_fileName,str_fileContent)

        f = open('ziparchive.zip','rb')

        return f


    def storeData(self, **kwargs):
        """
        Creates an object of the file and stores it into the container as key-value object 
        """

        for k,v in kwargs.items():
            if k == 'file_content':   str_fileContent = v
            if k == 'Path': 	      str_key         = v
            if k == 'is_zip':         b_zip       = v
            if k == 'd_ret':          d_ret       = v
            if k == 'client_path':    str_clientFile  = v

        try:
            self._initiateSwiftConnection()
            self._putContainer(str_key)
        except:
            d_ret['msg']    =  'Key already exists, use a different key'
            d_ret['status'] =  False
            return d_ret

        if not b_zip:
            str_fileContent_handler = self.zipUpContent(str_fileContent, str_clientFile)

        try:
            str_containerName = str_key
            str_key           = os.path.join('input','data')
            self._putObject(str_containerName, str_key, str_fileContent_handler)
        except Exception as err:
            self.qprint(err)
            d_ret['msg']    = 'File/Directory not stored in Swift'
            d_ret['status'] = False
            return d_ret
        finally:
            os.remove('ziparchive.zip')


        #Headers 
        d_ret['status'] = True
        d_ret['msg']    = 'File/Directory stored in Swift'

        return d_ret


    def getData(self, **kwargs):
        """
        Gets the data from the Swift Storage, zips and/or encodes it and sends it to the client
        """

        for k,v in kwargs.items():
            if k== 'path': str_key= v
            if k== 'is_zip': b_zip= v
            if k== 'encoding': str_encoding= v
            if k== 'cleanup': b_cleanup= v
            if k== 'd_ret': d_ret= v

        try:
            self._initiateSwiftConnection()
            self._downloadObject(str_key, False)
        except Exception as err:
            self.qprint(err)
            d_ret['status'] = False
            d_ret['msg']    = 'Retrieving File/Directory from Swift failed'
            return d_ret

        # [TODO Ashwin] replace with zip file read
        str_objectInformation= dataObject[0]
        str_fileContent= dataObject[1]
        
        #Unzipping
        if not b_zip:
            raise NotImplementedError('Please use the zip option')

        #Encoding
        if str_encoding =='base64':
            try:
                str_fileContent         = base64.b64encode(str_fileContent)
                self.qprint('Base64 encoding successful')

                d_fio               = {
                    'msg':            'Encode successful',
                    'status':         True
                }
                d_ret['encode']     = d_fio
                d_ret['status']     = d_fio['status']
                d_ret['msg']        = d_fio['msg']
                d_ret['timestamp']  = '%s' % datetime.datetime.now()

            except Exception as err:
                self.qprint(err)
                d_fio               = {
                    'msg':            'Encode unsuccessful',
                    'status':         False
                }
                d_ret['encode']     = d_fio
                d_ret['status']     = d_fio['status']
                d_ret['msg']        = d_fio['msg']
                d_ret['timestamp']  = '%s' % datetime.datetime.now()
                return d_ret              
        self.qprint("Transmitting " + Colors.YELLOW + " {} ".format(len(str_fileContent)) + Colors.PURPLE +
                        " target bytes from " + Colors.YELLOW + 
                        " swift store container {} ".format(str_key) + Colors.PURPLE + '...', comms = 'status')
        self.writeData(str_fileContent)
        
        #Transmit the file
        d_ret['status'] = True

        return d_ret


    def writeData(self, str_filePath):
        """
        Writes the file content into a wfile object for transferring over the network
        """
        self.send_response(200)
        # self.send_header('Content-type', 'text/json')
        self.end_headers()
        with open(str_filePath, 'rb') as fh:
                for chunk in iter(lambda: fh.read(4096), b''):
                    self.wfile.write(chunk)