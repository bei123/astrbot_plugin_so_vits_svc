import datetime
import hashlib
import hmac
from urllib.parse import quote
import json
import base64
import httpx
import asyncio
import sys

# ========== 用户需填写 =============
# ***REMOVED***
# ***REMOVED***
# appkey = "UyGuEnupum"
# ===================================

Service = "sami"
Version = "2021-07-27"
Region = "cn-north-1"
Host = "open.volcengineapi.com"
ContentType = "application/json"

def norm_query(params):
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for k in params[key]:
                query = (
                        query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&"
                )
        else:
            query = (query + quote(key, safe="-_.~") + "=" + quote(str(params[key]), safe="-_.~") + "&")
    query = query[:-1]
    return query.replace("+", "%20")

def hmac_sha256(key: bytes, content: str):
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()

def hash_sha256(content: str):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

async def volc_request(method, date, query, header, ak, sk, action, body):
    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": Service,
        "region": Region,
    }
    request_param = {
        "body": body,
        "host": Host,
        "path": "/",
        "method": method,
        "content_type": ContentType,
        "date": date,
        "query": {"Action": action, "Version": Version, **query},
    }
    if body is None:
        request_param["body"] = ""
    x_date = request_param["date"].strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = hash_sha256(request_param["body"])
    sign_result = {
        "Host": request_param["host"],
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": request_param["content_type"],
    }
    signed_headers_str = ";".join(
        ["content-type", "host", "x-content-sha256", "x-date"]
    )
    canonical_request_str = "\n".join(
        [request_param["method"].upper(),
         request_param["path"],
         norm_query(request_param["query"]),
         "\n".join(
             [
                 "content-type:" + request_param["content_type"],
                 "host:" + request_param["host"],
                 "x-content-sha256:" + x_content_sha256,
                 "x-date:" + x_date,
             ]
         ),
         "",
         signed_headers_str,
         x_content_sha256,
         ]
    )
    hashed_canonical_request = hash_sha256(canonical_request_str)
    credential_scope = "/".join([short_x_date, credential["region"], credential["service"], "request"])
    string_to_sign = "\n".join(["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request])
    k_date = hmac_sha256(credential["secret_access_key"].encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, credential["region"])
    k_service = hmac_sha256(k_region, credential["service"])
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()
    sign_result["Authorization"] = "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
        credential["access_key_id"] + "/" + credential_scope,
        signed_headers_str,
        signature,
    )
    header = {**header, **sign_result}
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=method,
            url=f"https://{request_param['host']}{request_param['path']}",
            headers=header,
            params=request_param["query"],
            content=request_param["body"]
        )
        return resp.json()

async def get_sami_token(ak, sk, appkey):
    now = datetime.datetime.utcnow()
    body = json.dumps({
        "appkey": appkey,
        "token_version": "volc-auth-v1",
        "expiration": 3600
    })
    resp = await volc_request("POST", now, {}, {}, ak, sk, "GetToken", body)
    token = resp.get("token")
    if not token:
        return None, resp
    return token, resp

async def detect_chorus_api(audio_bytes, volc_conf):
    ak = volc_conf["ak"]
    sk = volc_conf["sk"]
    appkey = volc_conf["appkey"]
    token, token_resp = await get_sami_token(ak, sk, appkey)
    if not token:
        return {"msg": "Token获取失败", "token_resp": token_resp}
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    body = json.dumps({"data": audio_b64})
    url = f"https://sami.bytedance.com/api/v1/invoke?version=v4&token={token}&appkey={appkey}&namespace=DeepChorus"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=body, headers={"Content-Type": "application/json"})
        if resp.status_code != 200:
            return {"msg": "副歌检测请求失败", "err": resp.text}
        result = resp.json()
        payload = result.get("payload")
        if payload:
            payload_json = json.loads(payload)
            chorus_list = payload_json.get("chorus_segments")
            if chorus_list and len(chorus_list) > 0:
                best = max(chorus_list, key=lambda x: x.get("chorus_prob", 0))
                interval = best.get("interval")
                if interval and len(interval) == 2:
                    return {"msg": "success", "chorus": {"start": interval[0], "end": interval[1]}}
                else:
                    return {"msg": "副歌区间格式异常", "raw": best}
            else:
                thumbnail = payload_json.get("thumbnail")
                if thumbnail and len(thumbnail) > 0:
                    interval = thumbnail[0].get("interval")
                    if interval and len(interval) == 2:
                        return {"msg": "success", "chorus": {"start": interval[0], "end": interval[1], "type": "高潮区间"}}
                    else:
                        return {"msg": "高潮区间格式异常", "raw": thumbnail[0]}
                else:
                    return {"msg": "未检测到明显的副歌区间"}
        else:
            return {"msg": "无payload返回", "raw": result}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python song.py <音频文件路径>")
        exit(1)
    audio_path = sys.argv[1]
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    result = asyncio.run(detect_chorus_api(audio_bytes))
    print(result)
