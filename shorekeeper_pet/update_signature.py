"""Ed25519 verification (RFC 8032) for update manifests. Verify-only and public data, so no secrets here."""
import base64,hashlib

# 本 fork 只信任自己的发布密钥：官方清单的 repository 字段也不匹配本仓库，
# 不可能被装上。私钥种子保存在维护者机器上，不随仓库分发。
PUBLIC_KEYS=(bytes.fromhex('9ab9013e79dd9dcf3606d7f9024983e5f5f1b93776e78ecc025816969fbf2c63'),)
P=2**255-19;L=2**252+27742317777372353535851937790883648493
D=-121665*pow(121666,P-2,P)%P;I=pow(2,(P-1)//4,P)

def _decode(raw):
    if len(raw)!=32:return None
    value=int.from_bytes(raw,'little');sign=value>>255;y=value&((1<<255)-1)
    if y>=P:return None
    x2=(y*y-1)*pow(D*y*y+1,P-2,P)%P
    if x2==0:
        if sign:return None
        x=0
    else:
        x=pow(x2,(P+3)//8,P)
        if (x*x-x2)%P:x=x*I%P
        if (x*x-x2)%P:return None
        if x&1!=sign:x=P-x
    return (x,y,1,x*y%P)

def _encode(point):
    inverse=pow(point[2],P-2,P);x=point[0]*inverse%P;y=point[1]*inverse%P
    return (y|(x&1)<<255).to_bytes(32,'little')

def _add(a,b):
    A=(a[1]-a[0])*(b[1]-b[0])%P;B=(a[1]+a[0])*(b[1]+b[0])%P
    C=2*a[3]*b[3]*D%P;E=2*a[2]*b[2]%P
    e,f,g,h=B-A,E-C,E+C,B+A
    return (e*f%P,g*h%P,f*g%P,e*h%P)

def _mul(scalar,point):
    result=(0,1,1,0)
    while scalar:
        if scalar&1:result=_add(result,point)
        point=_add(point,point);scalar>>=1
    return result

BASE=_decode((4*pow(5,P-2,P)%P).to_bytes(32,'little'))

def verify(message,signature,public_key):
    if len(signature)!=64:return False
    A=_decode(public_key);R=_decode(signature[:32]);S=int.from_bytes(signature[32:],'little')
    if A is None or R is None or S>=L:return False
    h=int.from_bytes(hashlib.sha512(signature[:32]+public_key+message).digest(),'little')%L
    return _encode(_mul(S,BASE))==_encode(_add(R,_mul(h,A)))

def _clamped_scalar(seed):
    if len(seed)!=32:raise ValueError('Ed25519 seed must be 32 bytes')
    digest=hashlib.sha512(seed).digest()
    scalar=int.from_bytes(digest[:32],'little')&((1<<254)-8)|(1<<254)
    return scalar,digest[32:]

def public_key(seed):
    """Derive the 32-byte public key for a 32-byte private seed."""
    scalar,_prefix=_clamped_scalar(seed)
    return _encode(_mul(scalar,BASE))

def sign(message,seed):
    """RFC 8032 sign with a raw 32-byte seed. Only maintainer tooling calls this."""
    scalar,prefix=_clamped_scalar(seed)
    public=_encode(_mul(scalar,BASE))
    r=int.from_bytes(hashlib.sha512(prefix+message).digest(),'little')%L
    R=_encode(_mul(r,BASE))
    k=int.from_bytes(hashlib.sha512(R+public+message).digest(),'little')%L
    return R+((r+k*scalar)%L).to_bytes(32,'little')

def verify_manifest(raw,text):
    # The mirror may carry these bytes, but only the release key can make them valid.
    try:signature=base64.b64decode(text.strip(),validate=True)
    except ValueError:signature=b''
    if not any(verify(raw,signature,key) for key in PUBLIC_KEYS):raise ValueError('更新清单签名校验失败，已取消更新')
