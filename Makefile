init:
	pip install -r requirements.txt

test:
	nosetests tests

readme:
	pandoc --from=rst --to=markdown --output=./README.md ./README.rst