# Windows shim for the Makefile targets.
#
# The Makefile is the contract — a reviewer on Linux or macOS runs `make eval`
# on a clean clone. GNU make isn't installed by default on Windows, so this
# mirrors the same targets: .\make.ps1 dataset -Seed 1337
#
# If you add a target to the Makefile, add it here too.

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'dataset', 'catalog', 'pairs', 'baseline', 'categories', 'rules', 'report', 'sample', 'eval', 'test', 'lint', 'clean')]
    [string]$Target = 'help',

    [int]$Seed = 1337,
    [int]$Size = 800
)

$ErrorActionPreference = 'Stop'
$py = 'python'
$catalog = 'data/generator/catalog.py'

switch ($Target) {
    'help' {
        Write-Host "setup     install dependencies"
        Write-Host "dataset   build the catalog and (later) the labelled pairs"
        Write-Host "eval      run the evaluation and rewrite eval/REPORT.md"
        Write-Host "test      run the test suite"
        Write-Host "report    catalog mapping coverage and composition"
        Write-Host "sample    print catalog samples"
        Write-Host "clean     remove generated artefacts (never data/raw)"
        Write-Host ""
        Write-Host "vars: -Seed $Seed -Size $Size"
    }
    'setup' {
        & $py -m pip install --upgrade pip
        & $py -m pip install -r requirements.txt
    }
    'catalog' { & $py $catalog --build --seed $Seed --size $Size }
    'pairs'   { & $py data/generator/make_dataset.py --build --seed $Seed }
    'dataset' {
        & $py $catalog --build --seed $Seed --size $Size
        & $py data/generator/make_dataset.py --build --seed $Seed
    }
    'baseline' { & $py eval/run_baseline.py --seed $Seed }
    'categories' { & $py eval/run_categories.py }
    'rules' { & $py eval/run_rules.py --seed $Seed }
    'report' { & $py $catalog --report --seed $Seed }
    'sample' { & $py $catalog --sample 40 --seed $Seed }
    'eval' {
        if (Test-Path 'eval/run_eval.py') {
            & $py eval/run_eval.py --seed $Seed
        }
        else {
            Write-Host "eval/run_eval.py not built yet - Milestone 2 onward."
            Write-Host "Available now: .\make.ps1 test, report, sample"
            exit 1
        }
    }
    'test' { & $py -m pytest -q }
    'lint' { & $py -m ruff check warrant data eval tests }
    'clean' {
        Remove-Item -Force -ErrorAction SilentlyContinue data/catalog/*.jsonl, data/gold/*.jsonl, eval/REPORT.md
        Get-ChildItem -Recurse -Directory -Include __pycache__, .pytest_cache |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}
