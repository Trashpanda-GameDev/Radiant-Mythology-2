# Radiant-Mythology-2
Attempt to complete English patch for Tales of the World: Radiant Mythology 2

# Unpacking Files
1. Use QuickBMS script `rm2_arc.bms` to unpack the `ARC` files.
2. Unpacking may have some errors with duplicate files, use the `s` option to skip them all for now.
3. Sample command: `quickbms.exe -d rm2_arc.bms D:\rm2\totw-rm2_original`
4. See `totw-rm2_extracted.txt` for list of files extracted.


# Repacking Files
1. Use QuickBMS script `rm2_arc.bms` to pack the `ARC` files.  Backup oroginal files!
2. Sample command: `quickbms.exe -r -w rm2_arc.bms D:\rm2\totw-rm2_original PSP_GAME`


# Hints
1. From the existing patch, it looks like the `PSPGAME\SYSDIR\EBOOT.BIN` is where most of the menu text is.
1. `PSP_GAME\USRDIR\quest\qdata.bin` was also translated
1. The `SCR` files are proabaly story/skit text

# Skit files
The `PSP_GAME\USRDIR\facechat\*.arc` contain the story/skit files
1. The `SCR` files contain the story/skit text
    1. The `SCR` files are compressed
    1. After decompression the `SCR` files are `EUC-JP` encoded
1. `PMF` files are video files
1. `AT3` files are audio files

Currently unknown file extensions
- `.PPT` unknown, probably the main talking head animation file

## Filenames in the facechat folder
- `ev####`/`ev####_#` are the main story dialogue files 

Currently unknown are filenames with the patterns: 
- `gv####` - 
- `sq###_##_###` - 
- `cv##_##` - 
- `facetest_#` - probably for debugging?
- `mapNAME_#` - probably names for map locations

# Resources
[QuickBMS script to unpack ARC files (PSP)](https://m.blog.naver.com/physics1114/220350378050)


# How-to:
1. Dump your ISO files inside the `0_disc` directory
    1. You should have something like: `0_disc/SYSDIR` & `0_disc/USRDIR`
    1. The main things that are expected here are `0_disc/USRDIR/facechat/` and `0_disc/USRDIR/npc/` because those are the ones we have XML files for atm
1. Change any xml files you want to translate by expanding the `<EnglishText/>` to `<EnglishText>`Any translated text goes here`</EnglishText>` 
    ```xml
    Example:
    
    <Entry>
        <PointerOffset/>
        <JapaneseText>ぼくもだ</JapaneseText>
        <EnglishText/>
        <Notes/>
        <SpeakerId>17</SpeakerId>
        <Id>1</Id>
        <Status>Editing</Status>
    </Entry>

    becomes:
    
    <Entry>
        <PointerOffset/>
        <JapaneseText>ぼくもだ</JapaneseText> <-- this stays intact
        <EnglishText>Me neither.</EnglishText> <-- this was added
        <Notes/>
        <SpeakerId>17</SpeakerId>
        <Id>1</Id>
        <Status>Editing</Status>
    </Entry> 
1. After having added new translations apply the changes to the `.ARC` files by running the python script `tools/rm2_apply.py`
    ```bash
    // example of an entire folder
    python tools\rm2_apply.py --target facechat --only ev0000_1 --pad-size --disc 0_disc --xml 2_translated --out 3_patched
    
    // example of a single file 
    python tools\rm2_apply.py --target facechat --only ev0000_1 --pad-size --disc 0_disc --xml 2_translated --out 3_patched
1. Now check if the folder `3_patched\USRDIR\facechat` or `3_patched\USRDIR\npc` has been created and if it contains the specified `.ARC` files.
1. Once the changes are applied to the `.ARC` files copy the files back to the UMD
    > I personally used `UMD-replace` in combination with a .bat file to run the command for all files in the folder
    > like so: 
    
    > UMD-replace example command:
    > ``` 
    > "UMD-replace.exe" "path_to\RM2_replaced.iso""PSP_GAME\USRDIR\facechat\ev0000.arc" "PATH_TO_REPO\3_patched\USRDIR\facechat\ev0000.arc"
    
    > replace-all.bat:
    > ```
    >     @echo off
    >     setlocal EnableExtensions EnableDelayedExpansion
    > 
    >     rem === EDIT THESE ===
    >     set "ISO=C:\[<< FULL PATH TO >>]\RM2_replaced.iso"
    >     set "TOOL=C:\[<< FULL PATH TO >>]\UMD-replace.exe"
    >     set "USRDIR=C:\[<< FULL PATH TO >>]\3_patched\USRDIR"
    > 
    >     rem Optional: only process these types
    >     set "GLOB=*.arc"
    > 
    >     if not exist "%ISO%"    echo ERROR: ISO not found: "%ISO%" & exit /b 1
    >     if not exist "%TOOL%"   echo ERROR: Tool not found: "%TOOL%" & exit /b 1
    >     if not exist "%USRDIR%" echo ERROR: USRDIR not found: "%USRDIR%" & exit /b 1
    > 
    >     rem Ensure BASE ends with backslash
    >     set "BASE=%USRDIR%"
    >     if not "%BASE:~-1%"=="\" set "BASE=%BASE%\"
    > 
    >     echo Replacing under:
    >     echo   Local: "%BASE%"
    >     echo   ISO:   "PSP_GAME\USRDIR\..."
    >     echo.
    > 
    >     for /r "%BASE%" %%F in (%GLOB%) do (
    >     set "ABS=%%~fF"
    >     call set "REL=%%ABS:%BASE%=%%"   rem e.g. facechat\ev0000_1.arc
    >     set "ISOPATH=PSP_GAME\USRDIR\!REL!"
    > 
    >     echo -> "!ISOPATH!"
    >     rem Normal (waits by default):
    >     "%TOOL%" "%ISO%" "!ISOPATH!" "%%~fF"
    >     if errorlevel 1 (
    >         echo FAILED: "!ISOPATH!"
    >         exit /b 1
    >     )
    > 
    >     rem If you ever see it not waiting, comment the line above and
    >     rem uncomment the next one to force waiting:
    >     rem start "" /wait "%TOOL%" "%ISO%" "!ISOPATH!" "%%~fF" || (echo FAILED: "!ISOPATH!" & exit /b 1)
    >     )
    > 
    >     echo.
    >     echo All done.
    >     endlocal
1. And voila you will have your patched and playable ISO.