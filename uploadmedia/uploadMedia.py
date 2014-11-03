import csv
import sys
import codecs
import time

# NB: the BMU facility uses methods from the "legacy" CGI webapps, imported below.
# Therefore, it must either be run from the directory where these modules live,
# or these modules must be copied to where the batch system (i.e. cron job) runs the script
#
# at the moment, the whole shebang expects to be run in /var/www/cgi-bin, and there are
# a couple of hardcoded dependencies below

CONFIGDIRECTORY = '/var/www/cgi-bin/'

from cswaUtils import postxml, relationsPayload, getConfig
from cswaDB import getCSID


def mediaPayload(f):
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<document name="media">
<ns2:media_common xmlns:ns2="http://collectionspace.org/services/media" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<blobCsid>%s</blobCsid>
<rightsHolder>%s</rightsHolder>
<creator>%s</creator>
<title>Media record</title>
<description>Contributors: %s</description>
<languageList>
<language>urn:cspace:bampfa.cspace.berkeley.edu:vocabularies:name(languages):item:name(eng)'English'</language>
</languageList>
<identificationNumber>%s</identificationNumber>
</ns2:media_common>
<ns2:media_bampfa xmlns:ns2="http://collectionspace.org/services/media/local/bampfa" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<approvedForWeb>true</approvedForWeb>
<primaryDisplay>false</primaryDisplay>
</ns2:media_bampfa>
</document>
"""
    payload = payload % (
        f['blobCsid'], f['rightsHolderRefname'], f['creator'], f['contributor'], f['objectNumber'])
    return payload


def uploadmedia(mediaElements, config):
    try:
        realm = config.get('connect', 'realm')
        hostname = config.get('connect', 'hostname')
        username = config.get('connect', 'username')
        password = config.get('connect', 'password')
    except:
        print "could not get config."
        raise

    objectCSID = getCSID('objectnumber', mediaElements['objectnumber'], config)
    if objectCSID == [] or objectCSID is None:
        print "could not get objectnumber's csid: %s." % mediaElements['objectnumber']
        raise
        #raise Exception("<span style='color:red'>Object Number not found: %s!</span>" % mediaElements['objectnumber'])
    else:
        objectCSID = objectCSID[0]
        mediaElements['objectCSID'] = objectCSID

        updateItems = {'objectStatus': 'found',
                       'subjectCsid': '',
                       'objectCsid': mediaElements['objectCSID'],
                       'objectNumber': mediaElements['objectnumber'],
                       'blobCsid': mediaElements['blobCSID'],
                       'rightsHolderRefname': mediaElements['rightsholder'],
                       'contributor': mediaElements['contributor'],
                       'creator': mediaElements['creator'],
                       'mediaDate': mediaElements['date'],
        }

        uri = 'media'

        #print "<br>posting to media REST API..."
        payload = mediaPayload(updateItems)
        (url, data, mediaCSID, elapsedtime) = postxml('POST', uri, realm, hostname, username, password, payload)
        #elapsedtimetotal += elapsedtime
        #print 'got mediacsid', mediaCSID, '. elapsedtime', elapsedtime
        mediaElements['mediaCSID'] = mediaCSID
        #print "media REST API post succeeded..."

        # now relate media record to collection object

        uri = 'relations'

        #print "<br>posting media2obj to relations REST API..."

        updateItems['objectCsid'] = objectCSID
        updateItems['subjectCsid'] = mediaCSID
        # "urn:cspace:bampfa.cspace.berkeley.edu:media:id(%s)" % mediaCSID

        updateItems['objectDocumentType'] = 'CollectionObject'
        updateItems['subjectDocumentType'] = 'Media'

        payload = relationsPayload(updateItems)
        (url, data, csid, elapsedtime) = postxml('POST', uri, realm, hostname, username, password, payload)
        #elapsedtimetotal += elapsedtime
        #print 'got relation csid', csid, '. elapsedtime', elapsedtime
        mediaElements['media2objCSID'] = csid
        #print "relations REST API post succeeded..."

        # reverse the roles
        #print "<br>posting obj2media to relations REST API..."
        temp = updateItems['objectCsid']
        updateItems['objectCsid'] = updateItems['subjectCsid']
        updateItems['subjectCsid'] = temp
        updateItems['objectDocumentType'] = 'Media'
        updateItems['subjectDocumentType'] = 'CollectionObject'
        payload = relationsPayload(updateItems)
        (url, data, csid, elapsedtime) = postxml('POST', uri, realm, hostname, username, password, payload)
        #elapsedtimetotal += elapsedtime
        #print 'got relation csid', csid, '. elapsedtime', elapsedtime
        mediaElements['obj2mediaCSID'] = csid
        #print "relations REST API post succeeded..."

    return mediaElements


class CleanlinesFile(file):
    def next(self):
        line = super(CleanlinesFile, self).next()
        return line.replace('\r', '').replace('\n', '') + '\n'


def getRecords(rawFile):
    #csvfile = csv.reader(codecs.open(rawFile,'rb','utf-8'),delimiter="\t")
    try:
        f = CleanlinesFile(rawFile, 'rb')
        csvfile = csv.reader(f, delimiter="|")
    except IOError:
        message = 'Expected to be able to read %s, but it was not found or unreadable' % rawFile
        return message,-1
    except:
        raise

    try:
        records = []
        for row, values in enumerate(csvfile):
            records.append(values)
        return records, len(values)
    except IOError:
        message = 'Could not read (or maybe parse) rows from %s' % rawFile
        return message,-1
    except:
        raise


if __name__ == "__main__":


    try:
        form = {'webapp': CONFIGDIRECTORY + sys.argv[2]}
        config = getConfig(form)
    except:
        print "MEDIA: could not get configuration"
        sys.exit()

    #print 'config',config
    records, columns = getRecords(sys.argv[1])
    if columns == -1:
        print 'MEDIA: Error! %s' % records
        sys.exit()
        
    print 'MEDIA: %s columns and %s lines found in file %s' % (columns, len(records), sys.argv[1])
    outputFile = sys.argv[1].replace('.step2.csv', '.step3.csv')
    outputfh = csv.writer(open(outputFile, 'wb'), delimiter="\t")

    for i, r in enumerate(records):

        elapsedtimetotal = time.time()
        mediaElements = {}
        for v1, v2 in enumerate(
                'name size objectnumber blobCSID date creator contributor rightsholder fullpathtofile'.split(' ')):
            mediaElements[v2] = r[v1]
        #print mediaElements
        if 'objectnumber' in mediaElements:
            mediaElements['objectnumber'] = mediaElements['objectnumber'].replace('.JPG','').replace('.jpg','')
        print 'objectnumber %s' % mediaElements['objectnumber']
        try:
            mediaElements = uploadmedia(mediaElements, config)
            print "MEDIA: objectnumber %s, objectcsid: %s, mediacsid: %s, %8.2f" % (
                mediaElements['objectnumber'], mediaElements['objectCSID'], mediaElements['mediaCSID'], (time.time() - elapsedtimetotal))
            r.append(mediaElements['mediaCSID'])
            r.append(mediaElements['objectCSID'])
            outputfh.writerow(r)
        except:
            print "MEDIA: create failed for objectnumber %s, %8.2f" % (
                mediaElements['objectnumber'], (time.time() - elapsedtimetotal))




