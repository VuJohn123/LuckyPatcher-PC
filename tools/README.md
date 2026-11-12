# LP-PC Suite - Tools

## Cau truc

```
tools/
|-- bin/                     # Executables & JARs
|   |-- apktool.jar          # Decompile / recompile APK
|   |-- baksmali.jar         # Dex -> Smali (fallback)
|   |-- smali.jar            # Smali -> Dex (fallback)
|   |-- uber-apk-signer.jar  # Sign APK
|   |-- bundletool.jar       # AAB -> APK
|   `-- GDA/                 # GDA.exe + runtime
|-- keys/                    # AOSP signing keys
|   |-- testkey.pk8, testkey.x509.pem
|   |-- platform.pk8, platform.x509.pem
|   |-- media.pk8, media.x509.pem
|   `-- shared.pk8, shared.x509.pem
|-- proxy_service/           # AIDL proxy smali (IAP emulation)
|-- scripts/
|   `-- extract_bundletool.py
`-- README.md
```

## Setup lan dau

```cmd
python tools\reorganize.py
```

Se:
1. Tao bin/, di chuyen JARs vao
2. Extract bundletool.jar tu bundletool.zip
3. Di chuyen GDA vao bin/GDA/
4. Di chuyen script vao scripts/
5. Xoa file zip cu sau khi extract

## Yeu cau

- Java 8+ (cho apktool, uber-apk-signer)
- Python 3.11+
- adb (optional - cai APK len thiet bi)
- openssl + keytool (optional - sign voi platform/media/shared keys)

## ⚠️ Quan trọng: Signing Keys

**Các file trong `tools/keys/` hiện tại là PLACEHOLDERS (9-17 bytes).**

```
media.pk8:           9 bytes  - "media.pk8"
platform.pk8:       12 bytes  - "platform.pk8"
shared.pk8:         10 bytes  - "shared.pk8"
testkey.pk8:        11 bytes  - "testkey.pk8"
media.x509.pem:     14 bytes  - "media.x509.pem"
platform.x509.pem:  17 bytes  - "platform.x509.pem"
shared.x509.pem:    15 bytes  - "shared.x509.pem"
testkey.x509.pem:   17 bytes  - " testkey.x509.pem"
```

**Ký APK với platform/media/shared/testkey SẼ THẤT BẠI** cho đến khi cung cấp AOSP keys thật.

### Cách lấy keys thật:

1. **Từ AOSP source tree** (cần build AOSP):
   ```
   build/target/product/security/testkey.pk8
   build/target/product/security/testkey.x509.pem
   build/target/product/security/platform.pk8
   build/target/product/security/platform.x509.pem
   build/target/product/security/media.pk8
   build/target/product/security/media.x509.pem
   build/target/product/security/shared.pk8
   build/target/product/security/shared.x509.pem
   ```

2. **Từ Android SDK platform-tools** (chỉ có testkey):
   - `apksigner` có thể dùng testkey mặc định

3. **Tự tạo testkey** (cho development):
   ```bash
   openssl genrsa -out testkey.pk8 2048
   openssl req -new -x509 -key testkey.pk8 -out testkey.x509.pem -days 10000 -subj "/CN=Android Debug/O=Android/C=US"
   openssl pkcs8 -topk8 -inform PEM -outform DER -in testkey.pk8 -out testkey.pk8 -nocrypt
   ```

### Mặc định:
- **testkey**: Dùng `uber-apk-signer.jar` (có embedded testkey) → **KHÔNG cần file pk8/pem**
- **platform/media/shared**: Cần AOSP keys thật + `apksigner` từ Android SDK build-tools

Xem `src/core/sign_with_key.py` để hiểu logic fallback.
