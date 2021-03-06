#!/usr/bin/env python2.7
"Checks list of hashes for malware names (using Virus Total)"

__author__ = 'hasherezade (hasherezade.net)'
__license__ = "GPL"
__VERSION__ = "1.0"

import sys,os
import re
import time
import zlib
import argparse
import urllib,urllib2

from hashlib import md5
from colorterm import *

DEFAULT_MALNAMES = 'cryptowall,crypwall,bunitu,proxy,zeus,zbot,ramnit'

host = "www.virustotal.com"
url2 = "https://" + host + "/en/search/?query="
method = 'GET'

agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:38.0) Gecko/20100101 Firefox/38.0 Iceweasel/38.2.1'
accept = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
language = 'en-US,en;q=0.5'
encoding = 'gzip, deflate'
content_type = "application/x-www-form-urlencoded"

g_DisableColors = False


class TimeoutException(Exception):
    pass

class FileInfo():
    def __init__(md5,name=None):
        self.md5 = md5
        self.name = name
        self.malname = None
        self.vendormalname = None
        self.keywords = set()

def decompress_data(data):
    data=zlib.decompress(data, 16+zlib.MAX_WBITS)
    return data

def make_req(host, url, mhash):
    data=''
    url += mhash
    print "\n---\n"+ url
    request = urllib2.Request(url, data, {'Host': host, 
        'Content-Type': content_type, 
        'User-Agent' : agent, 
        'Accept' : accept,
        'Accept-Language' : language,
        'Accept-Encoding' : encoding
    })
    request.get_method = lambda: method
    try:
        resp = urllib2.urlopen(request)
    except urllib2.HTTPError as e1:
        print "Error"
        raise e1
    except urllib2.URLError, e:
        print "Error"
        if 'timeout' in e.reason:
            raise TimeoutException()

    rcode = resp.getcode()
    if rcode == 200:
        resp_content = resp.read()  
        if resp.info().getheader('Content-Encoding') == 'gzip':
            resp_content = decompress_data(resp_content)
        return resp_content
    print "Response code: %d" % rcode
    return None

def fetch_md5s(line):
    pattern = '([0-9a-fA-F]{32})'
    md5 = re.findall(pattern, line)
    return md5

def get_hashes(fname):
    hashes = set()
    with open(fname, 'r') as f:
        for line in f.readlines():
            md5s = fetch_md5s(line)
            for md5 in md5s: 
                hashes.add(md5)
    return hashes

def md5sum(data):
    m = md5()
    m.update(data)
    return m.hexdigest()

def calc_hashes(dir_name):
    dir_content = set(os.listdir(dir_name))
    hash_to_name = dict()
    for fname in dir_content:
        fullname = dir_name + "//" + fname
        if not os.path.isfile(fullname):
            continue
        data = open(fullname, 'rb').read()
        md5 = md5sum(data)
        print md5 + " : " + fname
        hash_to_name[md5] = fname
    return hash_to_name

def get_between_patterns(data, pattern1, pattern2):
    pattern1 = pattern1.lower()
    pattern2 = pattern2.lower()
    data = data.lower()

    if not pattern1 in data:
        return None
    indx1 = data.index(pattern1) + len(pattern1)
    data = data[indx1:]
    if not pattern2 in data:
        return None
    indx2 = data.index(pattern2)
    data = data[:indx2].strip()
    return data

def check_keywords(data, keywords, mhash):
    data = data.lower()
    for keyword in keywords:
        keyword = keyword.lower().strip()
        if keyword in data:
            return keyword
    return None

def check_all_keywords(data, keywords, mhash):
    found_keywords = list()
    data = data.lower()
    for keyword in keywords:
        keyword = keyword.lower().strip()
        if keyword in data:
            found_keywords.append(keyword)
    if len(found_keywords) == 0:
        return None
    return found_keywords

def check_id(data, vendor):
    data = get_between_patterns(data, vendor, '</tr>')
    if not data:
        return None
    detectedp = '<td class=\"ltr text-red\">'
    not_detectedp = '<td class=\"ltr text-green\">'
    if get_between_patterns(data, not_detectedp, '</td>'):
        warn(vendor +": NOT DETECTED")
        return None

    fetched = get_between_patterns(data, detectedp, '</td>')
    if fetched:
        info(vendor + " : " + fetched)
    return fetched

def check_any(data):
    if not data:
        return None
    detectedp = '<td class=\"ltr text-red\">'
    fetched = get_between_patterns(data, detectedp, '</td>')
    return fetched

def get_names_table(data):
    if not data:
        return None
    detectedp = '<table class=\"table table-striped\" id=\"antivirus-results\">'
    fetched = get_between_patterns(data, detectedp, '<div class=\"tab-pane extra-info\" id=\"item-detail\">')
    return fetched

def vt_check(mhash, keywords, vendor, other_keywords=None):
    not_found = ["File not found"]

    try:
        resp_content = make_req(host, url2, mhash)
        if not resp_content:
            err("NO RESPONSE " + mhash)
            return None

        if check_keywords(resp_content, not_found, mhash):
            err("Not found: " + mhash)
            return None

        if other_keywords is not None:
            found_keywords = check_all_keywords(resp_content, other_keywords, mhash)
            if found_keywords is not None :
                found_str = ", ". join(found_keywords)
                info("KEYWORDS: " + found_str)

        vendor_id = check_id(resp_content, vendor) 
        if vendor_id is None :
            vendor_id = check_any(resp_content)
            if not vendor_id:
                err("NO VENDOR DETECTED : " + mhash)
                return None
            info("Other id : " + vendor_id)

        names_table = get_names_table(resp_content)
        malwarename = check_keywords(names_table, keywords, mhash)
        if malwarename :
            good(malwarename + " : " + mhash)
            return malwarename
        return vendor_id

    except TimeoutException:
        print "Timeout: " + url
    except urllib2.HTTPError as e:
        if e.code == 404:
            pass
        else:
            print "\tError : " + e.reason
    except Exception:
        pass
    return False

def write_to_file(f, item_info):
    f.write("%s\n" % item_info)

def write_list_to_file(filename, input_list):
    with open(filename, 'w') as f:
        for item in input_list:
            f.write("%s\n" % item)
    print "Saved: " + filename

def make_outfile_name(filename, prefix):
    basename = os.path.basename(filename)
    dirname = os.path.dirname(filename)

    basename = prefix + basename
    out_name = os.path.join(dirname, basename)
    return out_name

def main():
    parser = argparse.ArgumentParser(description="VirusTotal checker "+ __VERSION__)
    parser.add_argument('--hashes', dest="hashes", default=None, help="Input file with list of hashes (alternative to dir)")
    parser.add_argument('--dir', dest="dir", default=None, help="Input directory with files to scan")
    parser.add_argument('--names', dest="names", default=DEFAULT_MALNAMES, help="Searched malware names, ie. " + DEFAULT_MALNAMES)
    parser.add_argument('--keywords', dest="keywords", default=None, help="Other keywords searched in the report")
    parser.add_argument('--vendor', dest="vendor", default="Malwarebytes", help="Searched vendor, default='Malwarebytes'")
    parser.add_argument('--sleeptime', dest="sleeptime", default=3, help="Sleep time between queries, default=3", type=int)
    parser.add_argument('--nocolors', dest="nocolors", default="False", action='store_true', help="Disable colors?")
    args = parser.parse_args()

    global g_DisableColors
    g_DisableColors = args.nocolors

    found_list = list()
    not_found_list = list()

    if args.hashes is None and args.dir is None:
        print "[ERROR] Invalid parameters: supply dir or hashes!"
        return (-1)

    if args.hashes is not None and args.dir is not None:
        print "[ERROR] Invalid parameters: supply dir or hashes!"
        return (-1)

    if args.hashes is not None:
        hashes = get_hashes(args.hashes)
    input_name = args.hashes

    hash_to_name = None
    if args.dir is not None:
        hash_to_name = calc_hashes(args.dir)
        hashes = hash_to_name.keys()
        input_name = args.dir

    malnames = args.names.split(',')
    if args.keywords :
        keywords = args.keywords.split(',') 
    else:
        keywords = None

    for mhash in hashes:
        found = vt_check(mhash, malnames, args.vendor, keywords)
        if found:
            if hash_to_name is not None:
                name = hash_to_name[mhash]
                if name is not None:
                    print name
                    mhash = mhash + " : " + name
            found_list.append(mhash + " : " + found)
        else:
            not_found_list.append(mhash)
        time.sleep(args.sleeptime)
    print "----"
    print "Summary:"
    found_name = make_outfile_name( input_name, 'FOUND_')
    good("Found: " + str(len(found_list)))
    write_list_to_file(found_name, found_list)

    nfound_name = make_outfile_name(input_name, 'NOTFOUND_')
    err("Not Found: " + str(len(not_found_list)))
    write_list_to_file(nfound_name, not_found_list)
    print "----"
    return 1

if __name__ == "__main__":
    sys.exit(main())
