"""Read only existing official source references; never follow candidate hyperlinks.

Records document availability/exact host mentions, not ground-truth verification.
Self-site evidence remains pending; no live suspicious website is contacted.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,HTTPRedirectHandler,build_opener
from urllib.error import HTTPError,URLError
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from phishguard_vn.external_pilot import candidate_signature,url_views

TRUSTED_REFERENCE_HOSTS={'acb.com.vn','www.agribank.com.vn','bidv.com.vn','hoangvan.bacninh.gov.vn',
    'congan.quangngai.gov.vn','vpubnd.daklak.gov.vn','naict.tttt.nghean.gov.vn','mst.gov.vn',
    'vietnam.gov.vn','vnba.org.vn','corp.aeon.com.vn'}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def fetch(reference):
    checked=datetime.now(timezone.utc).isoformat()
    base={'checked_at_utc':checked,'http_status':'','body_sha256':'','text':''}
    if urlsplit(reference).scheme!='https' or urlsplit(reference).hostname not in TRUSTED_REFERENCE_HOSTS:
        return {**base,'status':'NOT_FETCHED_SELF_SITE_OR_UNAPPROVED_REFERENCE'}
    try:
        request=Request(reference,headers={'User-Agent':'PhishGuardVN-SourceEvidenceAudit/1.0'})
        with build_opener(NoRedirect()).open(request,timeout=15) as response:
            raw=response.read(5_000_001)
            base.update(http_status=str(response.status),body_sha256=hashlib.sha256(raw).hexdigest())
            if len(raw)>5_000_000:return {**base,'status':'OVERSIZED_DOCUMENT_NOT_ASSESSED'}
            if 'html' not in response.headers.get('Content-Type','').lower():
                return {**base,'status':'NONTEXT_DOCUMENT_NEEDS_REVIEW'}
            text=html.unescape(raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'))
            text=text.lower().replace('[.]','.').replace('(.)','.').replace('[:] ',':')
            return {**base,'status':'DOCUMENT_RETRIEVED','text':text}
    except HTTPError as e:return {**base,'status':'HTTP_ERROR_OR_REDIRECT_NOT_FOLLOWED','http_status':str(e.code)}
    except (URLError,TimeoutError,OSError) as e:
        # macOS framework Python may have no CA file. curl uses OS trust; never -k.
        if 'CERTIFICATE_VERIFY_FAILED' not in str(e) or not shutil.which('curl'):
            return {**base,'status':type(e).__name__+':'+str(e)[:160]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reference.bin'
            result=subprocess.run(['curl','--silent','--show-error','--max-time','15','--proto','=https',
                '--max-redirs','0','--output',str(path),'--write-out','%{http_code}\n%{content_type}',reference],
                capture_output=True,text=True,timeout=20)
            if result.returncode:return {**base,'status':'CURL_OS_TRUST_FETCH_FAILED:'+str(result.returncode)}
            status,_,content_type=result.stdout.partition('\n');raw=path.read_bytes()
            base.update(http_status=status,body_sha256=hashlib.sha256(raw).hexdigest())
            if status!='200':return {**base,'status':'CURL_HTTP_NON200_OR_REDIRECT_NOT_FOLLOWED'}
            if len(raw)>5_000_000 or 'html' not in content_type.lower():return {**base,'status':'CURL_NONTEXT_OR_OVERSIZED_NEEDS_REVIEW'}
            text=html.unescape(raw.decode('utf-8',errors='replace')).lower().replace('[.]','.').replace('(.)','.')
            return {**base,'status':'DOCUMENT_RETRIEVED_VIA_CURL_OS_TRUST','text':text}


def main():
    current=pd.concat([pd.read_csv(ROOT/'data/external'/p,dtype=str,keep_default_na=False,encoding='utf-8')
                       for p in ['phishing_candidates.csv','benign_candidates.csv']],ignore_index=True)
    refs=sorted(set(current.evidence_ref))
    with ThreadPoolExecutor(max_workers=4) as pool: sources=dict(zip(refs,pool.map(fetch,refs)))
    records=[]
    for r in current.to_dict('records'):
        view=url_views(r['url']); source=sources[r['evidence_ref']];host=view['hostname']
        seen=bool(host and re.search(r'(?<![a-z0-9_.-])'+re.escape(host)+r'(?![a-z0-9_.-])',source['text']))
        signature=candidate_signature({'id':r['id'],'raw_url':r['url'],'label':r['label'],
                                       'source':r['source'],'source_reference':r['evidence_ref']})
        records.append({'id':r['id'],'candidate_signature':signature,'source_reference_checked':r['evidence_ref'],
            'source_document_status':source['status'],'reference_http_status':source['http_status'],
            'reference_body_sha256':source['body_sha256'],'source_host_seen':seen,'source_checked_at_utc':source['checked_at_utc'],
            'source_check_limit':'AI-assisted document check only; host mention is not current site/label verification. Images/PDF/JS may require manual review. No candidate hyperlink visited.'})
    out=ROOT/'reports/annotations/k53_source_checks.csv'
    pd.DataFrame(records).to_csv(out,index=False,encoding='utf-8',lineterminator='\n')
    print(json.dumps({'reference_count':len(refs),'reference_statuses':pd.Series([s['status'] for s in sources.values()]).value_counts().to_dict(),
                      'candidate_host_seen_in_reference':sum(r['source_host_seen'] for r in records),
                      'labels_promoted_to_verified':0},indent=2,ensure_ascii=False))


if __name__=='__main__':main()
