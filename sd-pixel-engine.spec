block_cipher = None

a = Analysis(['sd_pixel_engine/__main__.py'],
             pathex=[],
             binaries=None,
             datas=None,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[  
               'PySide6.QtWebChannel', 
               'PySide6.QtWebEngineCore', 
               'PySide6.QtWebEngineWidgets',
               'PySide6.QtWebContext',
               'PySide6.QtNetwork',
               'PySide6.QtCore',
               'PySide6.QtGui',
               'PySide6.QtSvg',
               'PySide6.QtWidgets',
               'PySide6.QtSvg',
               'PySide6.QtQuick',
               'PySide6.QtQml',
            ],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='sd-pixel-engine',
          contents_directory=".",
          debug=False,
          strip=False,
          upx=True,
          console=True )
          
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='sd-pixel-engine')