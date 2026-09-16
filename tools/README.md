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
