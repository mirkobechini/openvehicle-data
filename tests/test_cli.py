from pipeline.cli import cli


def test_cli_parses_and_prints_the_result(capsys):
    cli("prog", [(("--n",), {"type": int, "default": 2}), (("--name",), {"required": True})], lambda a: {"n": a.n, "name": a.name}, ["--name", "x"])
    assert capsys.readouterr().out.strip() == "{'n': 2, 'name': 'x'}"
