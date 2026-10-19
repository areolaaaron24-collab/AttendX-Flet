# Platform and hardware support

The Flet project is structured for Windows/Linux desktop and future Android/iOS packaging. **Packaging the UI is not proof that all peripherals work on every platform.** This project has not been built or acceptance-tested on four operating systems in this environment.

## Desktop

### Windows

```powershell
pip install -r requirements-desktop.txt
python main.py
flet build windows
```

For a Windows executable, use a compatible Python/Flet toolchain and install Visual Studio Build Tools with the **Desktop development with C++** workload if the build tool requires it. Webcam permissions, antivirus policy, device drivers and the chosen serial adapter must be checked on the actual Windows computer.

### Linux

```bash
pip install -r requirements-desktop.txt
python main.py
flet build linux
```

Install your distribution's system packages required by Flet, camera/OpenCV, Qt/GTK or native Python dependencies before packaging. Check `/dev/video*` camera permissions and serial permissions (for example, group membership and udev rules) for USB devices. Do not run as root just to bypass device access.

## Android

```bash
flet build apk
# Or a store-oriented Android App Bundle:
flet build aab
```

Install/configure a supported JDK (17 is the documented baseline in the Flet build guide) and Android SDK; grant and test requested app permissions on a real phone. The current camera scanning path imports desktop OpenCV lazily and reports when it is unavailable; a native mobile camera/QR integration still needs to be implemented and tested. The planned phone fingerprint flow is Android's native BiometricPrompt for the currently signed-in student's own device. It confirms a local biometric authentication; Android does not provide AttendX with a reusable fingerprint image/template and it cannot identify students on a shared phone. A server-authorized student self-attendance RPC must bind the signed-in identity to an enrolled schedule before this can be used for attendance. That native integration and server-side authorization are not implemented/verified yet. Mobile face recognition cannot be assumed to support dlib wheels and needs a mobile-compatible capture/recognition implementation.

## iOS

```bash
flet build ipa
# A simulator build may be available through the installed Flet CLI:
flet build ipa --help
```

The iOS build must be run on macOS with the relevant Xcode/iOS SDK, signing certificate, provisioning profile and device setup. Apple account/signing and App Store submission are manual steps. Camera UI and permissions need a native-compatible implementation and real iPhone testing. USB serial fingerprint attendance is not supported by the current desktop adapter on iOS.

## Feature compatibility summary

| Capability | Windows/Linux desktop | Android/iOS |
|---|---|---|
| Flet screens/forms/navigation | Intended target; runtime test pending | Packaging intended; device QA pending |
| Supabase Auth/PostgreSQL | Network connection required | Network connection required |
| Excel/CSV/PDF generation | Intended; verify save/open paths | Verify app sandbox/export/share UX |
| QR session/pass display | Intended | Intended; device testing needed |
| Camera QR scanning | Requires desktop camera adapter/dependency | Native camera scanning not yet implemented/verified |
| Face recognition | Optional native face-recognition/dlib packages; not hardware-tested | Student self-registration is in the UI, but mobile-compatible capture/recognition is not implemented/verified |
| Phone fingerprint authentication | Not available in this desktop build | Planned Android BiometricPrompt for the signed-in student; native prompt and server-authorized self-attendance are not implemented/verified |

Until a hardware test is completed, tell operators to use a configured, authorized QR workflow as the supported alternative when camera scanning is available. If QR scanning is not available either, use a teacher-authorized, reason-recorded manual attendance correction only if that workflow is enabled by database policy; never invent or silently record a successful scan.

## Official Flet build references

Check the Flet documentation at build time because platform requirements change: <https://docs.flet.dev/publish/> and <https://docs.flet.dev/cli/flet-build/>. Windows application packaging should be built on Windows, Linux packaging on Linux, and iOS/IPA packaging on macOS with Apple's tools. Android builds need the Android toolchain. Confirm exact SDK/toolchain versions against your installed Flet version before production packaging.
