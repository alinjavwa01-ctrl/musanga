#!/usr/bin/env python3
"""KYC and limited mode, against a running server. Usage: python3 tests_kyc.py [port]"""
import base64, json, sys, time, urllib.request, urllib.error
N = int(time.time()) % 100000
PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"
BASE = "http://127.0.0.1:%s" % PORT
def call(m,p,b=None,t=None):
    h={"Content-Type":"application/json"}
    if t: h["Authorization"]="Bearer "+t
    r=urllib.request.Request(BASE+p,method=m,data=json.dumps(b).encode() if b is not None else None,headers=h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.load(x)
    except urllib.error.HTTPError as e: return e.code, json.load(e)

P=F=0
def check(n,c,x=""):
    global P,F
    if c: P+=1; print("  ok    "+n)
    else: F+=1; print("  FAIL  %s  %s"%(n,x))

s,r=call("POST","/api/auth/register",{"role":"shipper","name":"Test Buyer","phone":"+26097%05d" % N,"email":"t@x.zm","company":"Testco","password":"musanga2026"})
check("signup needs only four fields", s==200 and r["user"]["kyc_status"]=="unverified", r)
tok=r["token"]
check("new account is in limited mode", r["user"]["verified"] is False and r["user"]["can"]["book_load"] is False, r["user"])

s,o=call("POST","/api/orders",{"equipment":"flatbed30","service":"spot","commodity":"maize","from_zone":"mkushi","to_zone":"lusaka","pickup_address":"a","dropoff_address":"b","recipient_name":"c","recipient_phone":"+260970000000","goods":"maize","tonnes":30,"payment_method":"card"},tok)
check("unverified cannot book", s==403 and "Verify" in o["error"], o)
s,q=call("POST","/api/quote",{"equipment":"flatbed30","service":"spot","commodity":"maize","from_zone":"mkushi","to_zone":"lusaka","tonnes":30})
check("unverified can still rate a load", s==200 and q["total_ngwee"]>0, s)

s,k=call("GET","/api/kyc",None,tok)
check("checklist is waiting in the app", s==200 and k["documents_required"]>=7 and k["blockers"], (s,k.get("documents_required")))
s,k=call("POST","/api/kyc/submit",None,tok)
check("cannot submit an empty file", s==400, k)

s,k=call("POST","/api/kyc/profile",{"entity_type":"limited","legal_name":"Testco Limited","trading_name":"Testco","reg_number":"120990","tin":"1002000999","country":"ZM","address":"Plot 5, Lusaka","sector":"agriculture","vat_registered":True,"vat_number":"VAT99"},tok)
check("business details save", s==200 and not k["missing_fields"], k.get("missing_fields"))
check("VAT certificate becomes mandatory", any(d["key"]=="vat_cert" and d["mandatory"] for d in k["checklist"]), "")

s,k=call("POST","/api/kyc/people",{"full_name":"Ali Njavwa","position":"Director","id_type":"nrc","id_number":"123456/78/9","ownership_pct":100,"is_control":True},tok)
check("a control person can be named", s==200 and not k["people_problems"], k.get("people_problems"))

pdf=base64.b64encode(b"%PDF-1.4 test").decode()
for item in k["checklist"]:
    if item["mandatory"]:
        s,k2=call("POST","/api/kyc/documents",{"doc_key":item["key"],"file":"data:application/pdf;base64,"+pdf,"filename":item["key"]+".pdf","reference":"REF1"},tok)
        if s!=200: check("filing %s"%item["key"], False, k2); break
else:
    check("every required document files", not k2["blockers"], k2["blockers"])

s,bad=call("POST","/api/kyc/documents",{"doc_key":"cert_incorporation","file":"data:application/zip;base64,"+pdf,"filename":"x.zip"},tok)
check("a zip is refused", s==400, bad)
s,bad=call("POST","/api/kyc/documents",{"doc_key":"not_a_document","reference":"x"},tok)
check("an unknown document is refused", s==400, bad)

s,k=call("POST","/api/kyc/submit",None,tok)
check("a complete file submits", s==200 and k["status"]=="in_review", k.get("status"))
s,locked=call("POST","/api/kyc/profile",{"legal_name":"Changed"},tok)
check("a file in review is frozen", s==400, locked)

s,me=call("GET","/api/me",None,tok)
check("me carries the state", me["kyc"]["status"]=="in_review", me.get("kyc"))

s,ops=call("POST","/api/auth/login",{"phone":"+260970000001","password":"musanga2026"})
optok=ops["token"]
check("staff bypass the queue", ops["user"]["verified"] is True, ops["user"])
s,queue=call("GET","/api/ops/kyc",None,optok)
check("the applicant is in the queue", s==200 and any(a["status"]=="in_review" for a in queue["applicants"]), queue.get("waiting"))
uid=[a["id"] for a in queue["applicants"] if a["phone"]==("+26097%05d" % N)][0]
s,one=call("GET","/api/ops/kyc/%d"%uid,None,optok)
check("compliance sees the whole file", s==200 and one["people"] and one["profile"]["tin"]=="1002000999", s)

s,d=call("POST","/api/ops/kyc/%d/decision"%uid,{"decision":"rejected"},optok)
check("a rejection must say why", s==400, d)
s,d=call("POST","/api/ops/kyc/%d/decision"%uid,{"decision":"rejected","note":"PACRA printout is older than six months","reject_documents":["pacra_printout"]},optok)
check("a file can be sent back", s==200 and d["status"]=="rejected", d.get("status"))
s,k=call("GET","/api/kyc",None,tok)
check("the applicant sees why", k["note"].startswith("PACRA") and any(c["status"]=="rejected" for c in k["checklist"]), k.get("note"))
check("the rejected document is outstanding again", any(c["key"]=="pacra_printout" and not c["filed"] for c in k["checklist"]), "")

s,k=call("POST","/api/kyc/documents",{"doc_key":"pacra_printout","file":"data:application/pdf;base64,"+pdf,"filename":"pacra.pdf"},tok)
s,k=call("POST","/api/kyc/submit",None,tok)
check("it can be fixed and resubmitted", s==200 and k["status"]=="in_review", k)
s,d=call("POST","/api/ops/kyc/%d/decision"%uid,{"decision":"verified","note":"Cleared"},optok)
check("and then verified", d["status"]=="verified", d.get("status"))

s,me=call("GET","/api/me",None,tok)
check("the account leaves limited mode", me["user"]["verified"] is True and me["user"]["can"]["book_load"], me["user"])
s,o=call("POST","/api/orders",{"equipment":"flatbed30","service":"spot","commodity":"maize","from_zone":"mkushi","to_zone":"lusaka","pickup_address":"a","dropoff_address":"b","recipient_name":"c","recipient_phone":"+260970000000","goods":"maize","tonnes":30,"payment_method":"invoice"},tok)
check("and can book on invoice terms", s==200 and (o.get("order") or o).get("ref"), o)

doc_id=[c["document"]["id"] for c in call("GET","/api/kyc",None,tok)[1]["checklist"] if c["document"]][0]
s,f=call("GET","/api/kyc/documents/%d/file"%doc_id,None,tok)
check("the owner can open their file", s==200 and f["content"], s)
s,r2=call("POST","/api/auth/register",{"role":"driver","name":"Nosy","phone":"+26098%05d" % N,"password":"musanga2026"})
s,f2=call("GET","/api/kyc/documents/%d/file"%doc_id,None,r2["token"])
check("another account cannot", s==404, s)

print("\n  %d passed, %d failed" % (P,F))
raise SystemExit(1 if F else 0)
