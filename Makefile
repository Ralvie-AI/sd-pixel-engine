build:
	poetry install

package:
	pyinstaller sd-pixel-engine.spec --clean --noconfirm

clean:
	rm -rf build dist
	rm -rf sd_pixel_engine/__pycache__

