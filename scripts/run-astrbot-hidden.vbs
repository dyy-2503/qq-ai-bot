Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "<INSTALL_DIR>"
sh.Run "cmd /c ""<INSTALL_DIR>\start-astrbot.bat""", 0, False
