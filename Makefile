build:
	poetry install

package:
	pyinstaller sd-screen-shot.spec --clean --noconfirm

clean:
	rm -rf build dist
	rm -rf sd_screen_shot/__pycache__

