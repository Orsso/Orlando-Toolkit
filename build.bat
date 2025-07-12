@echo off
setlocal enabledelayedexpansion

:: Build script for Orlando Toolkit Windows executable
:: Run this from the project root directory

cls
echo.
echo                                   ***               
echo                                 +++++++             
echo                                *+++++++*            
echo                                 +++++++             
echo                         ++++++**+++++++**++++++     
echo                         *++++++++++*++++++++++*     
echo                          +++++*#########*+++++      
echo                          ++++####o   o####+++       
echo                     ++++++++###o  --   o###++++++++ 
echo                    +++++++++###  -----  ###+++++++++
echo                    *++++++++###   ---   ###++++++++*
echo                      **  +++*###       ###*+++  **  
echo                          +++++###########+++++      
echo                          +++++++#######++++++       
echo                         ++++++++++***+++++++++*     
echo                          +++++++*     *+++++++      
echo                             ++++*     *++++         
echo                                 *     *    
echo.
echo                 Welcome to the O R L A N D O  T O O L K I T builder!
echo.
echo                                 Version 1.0                            
echo.
echo   +-- BUILD OVERVIEW -------------------------------------------------------+
echo   ^|                                                                        ^|
echo   ^| This script will guide you through building the Orlando Toolkit.       ^|
echo   ^| It will automatically:                                                 ^|
echo   ^|   1. Check for a suitable Python environment (or set one up for you^).  ^|
echo   ^|   2. Install all necessary build tools and dependencies.               ^|
echo   ^|   3. Compile the application into a single executable file.            ^|
echo   ^|                                                                        ^|
echo   +------------------------------------------------------------------------+
echo.
echo   Press any key to begin...
pause >nul

:: =============================================================================
:: SECOND PAGE - BUILD PROCESS
:: =============================================================================

cls
echo   +======================================================================+
echo   ^|                         O R L A N D O                                ^|
echo   ^|                         T O O L K I T                                ^|
echo   ^|                         Build Process                                ^|
echo   +======================================================================+
echo.
echo   +---[ Step 1 of 3: Checking Python Environment ]-----------------------+
echo.

:: Check if Python is available
set "PYTHON_CMD=python"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   System-wide Python not found.
    echo   Setting up a temporary, self-contained Python runtime...
    call :setup_portable_python
) else (
    echo   Using existing Python installation found on your system.
)

echo.
echo   +---[ Python environment ready. ]--------------------------------------+

:: =============================================================================
:: BUILD TOOLS AND COMPILATION
:: =============================================================================

echo.
echo   +---[ Step 2 of 3: Installing Dependencies ]---------------------------+
echo.

:: Check if PyInstaller is available
"%PYTHON_CMD%" -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing core build utility ^(PyInstaller^)...
    "%PYTHON_CMD%" -m pip install pyinstaller --no-warn-script-location
    rem pip may exit with code 1 when it just prints an update notice - treat 0/1 as success
    if %errorlevel% gtr 1 (
        echo.
        echo   ERROR: Failed to install the build utility.
        pause
        exit /b 1
    )
) else (
    echo   Core build utility ^(PyInstaller^) is already present.
)

echo   Installing application dependencies ^(lxml, Pillow, etc.^)...
"%PYTHON_CMD%" -m pip install -r requirements.txt --no-warn-script-location
if %errorlevel% gtr 1 (
    echo.
    echo   ERROR: Failed to install required application dependencies.
    pause
    exit /b 1
)

echo.
echo   +---[ Dependencies installed successfully. ]---------------------------+
echo.
echo   +---[ Step 3 of 3: Building the Application ]--------------------------+
echo.
echo   This final step may take a few moments. Please wait...
echo.

:: Run the build script
"%PYTHON_CMD%" build_exe.py

if %errorlevel% equ 0 (
    cls
    echo   +======================================================================+
    echo   ^|                                                                      ^|
    echo   ^|                          B U I L D   S U C C E S S F U L             ^|
    echo   ^|                                                                      ^|
    echo   +======================================================================+
    echo.
    echo   The application has been created successfully!
    echo.
    echo   You can find OrlandoToolkit.exe inside the 'release' folder.
    echo.
    echo   +----------------------------------------------------------------------+
    echo.
    echo   This build process created some temporary files and folders:
    echo     - build/
    echo     - release/ (contains the final .exe)
    echo     - tools/ (contains the portable Python runtime)
    echo     - OrlandoToolkit.spec
    echo.
    choice /c YN /m "Would you like to remove the temporary 'build' and 'tools' folders?"
    if errorlevel 2 (
        echo.
        echo   Cleanup skipped. The 'release' folder with your .exe is preserved.
    ) else (
        echo.
        echo   Cleaning up temporary files...
        rmdir /s /q "build" >nul 2>&1
        rmdir /s /q "tools" >nul 2>&1
        del "*.spec" >nul 2>&1
        echo   Cleanup complete.
    )
    goto :end_of_script
) else (
    echo   +======================================================================+
    echo   ^|                                                                      ^|
    echo   ^|                             B U I L D   F A I L E D                  ^|
    echo   ^|                                                                      ^|
    echo   +======================================================================+
    echo.
    echo     An error occurred during the build process.
    echo     Please review the messages above for specific details.
    echo.
)

echo.
echo   Press any key to exit...
pause >nul
:end_of_script
goto :EOF

:: =============================================================================
:: FUNCTIONS
:: =============================================================================

:setup_portable_python
:: ----------------------------------------------------------------------
:: Download and extract a WinPython "dot" portable package (includes tkinter)
:: ----------------------------------------------------------------------

echo.
echo   +---------------------------------------------------------------------+
echo   ^|       Setting up a self-contained Python environment...             ^|
echo   +---------------------------------------------------------------------+
echo.

:: Create tools directory
if not exist "tools" mkdir tools

:: If we already have a python.exe cached - reuse it -----------------------
for %%F in (tools\**\python.exe) do (
    set "PYTHON_FOUND=%%F"
    goto :python_ready
)

:: Choose WinPython version (64-bit, small "dot" build)
set "WPCODE=5.0.20221030final"
set "WPFILENAME=Winpython64-3.10.8.0dot.exe"
set "WPDL_URL=https://github.com/winpython/winpython/releases/download/%WPCODE%/%WPFILENAME%"
set "WP_SFX=tools\%WPFILENAME%"

echo   Downloading a lightweight Python runtime...
powershell -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%WPDL_URL%', '%WP_SFX%')"
if not exist "%WP_SFX%" (
    echo.
    echo   ERROR: Could not download the required Python package.
    echo   Please check your internet connection.
    pause
    exit /b 1
)

echo   Setting up the Python runtime...
"%WP_SFX%" -y -o"tools" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Extraction of the Python runtime failed.
    pause
    exit /b 1
)

:: Remove any legacy embeddable python leftovers that may shadow WinPython
if exist "tools\python\python.exe" rmdir /s /q "tools\python" >nul 2>&1

:: Locate python.exe prioritising WPy directories
set "PYTHON_FOUND="

:: Prefer real interpreter in tools\WPy*\python-* folder (file size > 50000 bytes)
for %%F in (tools\WPy*\python-*.*\python.exe) do (
    for %%S in (%%~zF) do if %%S GTR 50000 (
        set "PYTHON_FOUND=%%~F"
        goto :python_ready
    )
)

:: Absolute fallback - first python.exe >50 KB anywhere under tools
for /r "tools" %%F in (python.exe) do (
    for %%S in (%%~zF) do if %%S GTR 50000 (
        set "PYTHON_FOUND=%%~F"
        goto :python_ready
    )
)

echo.
echo   ERROR: python.exe not found after extraction.
exit /b 1

:python_ready
rem Store path without embedded quotes; we will add them when executing.
set "PYTHON_CMD=%PYTHON_FOUND%"

:: Install pip if missing (WinPython ships without ensurepip in dot build)
"%PYTHON_CMD%" -m ensurepip --default-pip >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'tools\get-pip.py'" >nul 2>&1
    "%PYTHON_CMD%" tools\get-pip.py --quiet --no-warn-script-location
    del tools\get-pip.py >nul 2>&1
)

echo.
echo   +--- Verifying Graphics Support ------------------------------------+
"%PYTHON_CMD%" -c "import tkinter, sys; print('tkinter OK -', tkinter.TkVersion)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: The required graphical interface component ^(tkinter^)
    echo   is missing or failed to load. Aborting build.
    exit /b 1
)

echo   +--- Python environment setup is complete. -------------------------+
echo.
exit /b 0