block_cipher = None
excludes_package = ["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore"]
a = Analysis(['sd_pixel_engine/__main__.py'],
             pathex=[],
             binaries=None,
             datas=None,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=excludes_package,
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