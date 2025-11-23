import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from pydantic_ai import Agent
from rich.console import Console

# Load environment variables from .env file if present
load_dotenv()

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()

AECH_MANIFEST = {
    "name": "translator",
    "type": "cli",
    "description": (
        "Run an end-to-end enterprise translation workflow. Given a Markdown"
        " source and optional enterprise context, the CLI translates to the"
        " requested language, back-translates for QA, and writes two files to"
        " the caller-provided output directory: `<stem>_<lang>.md` containing"
        " the translated Markdown and `<stem>_translation_report.md` summarizing"
        " QA (overall quality: Pass/Needs Review/Fail, key discrepancies,"
        " recommendations). Automations should attach both files and include a"
        " short QA summary in the response to the requester. Example:"
        " `aech-cli-translator translate docs/blog.md es --context termbase.md"
        " --output-dir out/translations`."
    ),
    "command": "aech-cli-translator",
    "actions": [
        {
            "name": "translate",
            "description": (
                "Translate a Markdown document into a target language, optionally"
                " applying enterprise context. Outputs two files in `output_dir`:"
                " `<stem>_<lang>.md` with the translated Markdown and"
                " `<stem>_translation_report.md` with QA from the back-translation"
                " (overall quality, discrepancies, recommendations). Example:"
                " `translate proposal.md fr --context brand-guide.md --output-dir"
                " build/locale`."
            ),
            "parameters": [
                {"name": "input_file", "type": "argument", "required": True},
                {"name": "target_lang", "type": "argument", "required": True},
                {"name": "context", "type": "option", "required": False},
                {"name": "output_dir", "type": "option", "required": True},
            ],
        }
    ],
    "available_in_sandbox": True,
}


@app.callback(invoke_without_command=False)
def main() -> None:
    """Aech CLI Translator root command."""


def _should_emit_manifest(argv: list[str]) -> bool:
    """Return True when CLI should output the manifest instead of help text."""

    return len(argv) == 2 and argv[1] in ("-h", "--help")


def _print_manifest() -> None:
    print(json.dumps(AECH_MANIFEST, indent=2))

# Define Agents
translator_agent = Agent(
    'openai:gpt-4.1',
    system_prompt=(
        "You are an expert enterprise translator. "
        "Translate the content accurately, preserving formatting (Markdown). "
        "Use the provided Enterprise Context to ensure correct terminology. "
        "Do not add conversational filler. Output ONLY the translated markdown."
    )
)

back_translator_agent = Agent(
    'openai:gpt-4.1',
    system_prompt=(
        "You are an expert translator. "
        "Translate the text back to the original language (English/Source). "
        "Output ONLY the translated markdown."
    )
)

auditor_agent = Agent(
    'openai:gpt-4.1',
    system_prompt=(
        "You are a Translation Quality Assurance Auditor. "
        "Compare the Original Text and the Back-Translated Text. "
        "Identify any significant discrepancies in meaning, tone, or terminology. "
        "Ignore minor phrasing differences if the meaning is preserved. "
        "Output a Markdown report with: "
        "- Overall Quality Assessment (Pass/Fail/Needs Review) "
        "- Key Discrepancies (if any) "
        "- Recommendations"
    )
)

async def run_translation_flow(input_path: Path, target_lang: str, context_text: str, out_path: Path):
    source_text = input_path.read_text()

    # 1. Translate
    console.print(f"[blue]Translating {input_path.name} to {target_lang}...[/blue]")
    
    translation_prompt = f"""
    Target Language: {target_lang}
    
    Enterprise Context:
    {context_text}
    
    Content to Translate:
    {source_text}
    """
    
    result = await translator_agent.run(translation_prompt)
    translated_text = result.output
    
    # Save translation
    translated_filename = f"{input_path.stem}_{target_lang}.md"
    translated_file = out_path / translated_filename
    translated_file.write_text(translated_text)
    console.print(f"[green]Translation saved to {translated_file}[/green]")

    # 2. Back-Translate
    console.print(f"[blue]Back-translating for verification...[/blue]")
    back_translation_prompt = f"""
    Translate the following {target_lang} text back to the original language:
    {translated_text}
    """
    
    bt_result = await back_translator_agent.run(back_translation_prompt)
    back_translated_text = bt_result.output

    # 3. Verify / Generate Report
    console.print(f"[blue]Generating Quality Report...[/blue]")
    report_prompt = f"""
    Original Text:
    {source_text}
    
    Back-Translated Text:
    {back_translated_text}
    """
    
    report_result = await auditor_agent.run(report_prompt)
    report_text = report_result.output
    
    # Save report
    report_filename = f"{input_path.stem}_translation_report.md"
    report_file = out_path / report_filename
    report_file.write_text(report_text)
    console.print(f"[green]Report saved to {report_file}[/green]")
    
    print(json.dumps({
        "translated_file": str(translated_file),
        "report_file": str(report_file)
    }))

@app.command(name="translate")
def translate(
    input_file: str = typer.Argument(..., help="Input file path"),
    target_lang: str = typer.Argument(..., help="Target language code"),
    context_file: Optional[str] = typer.Option(None, "--context", "-c", help="Path to a markdown file containing enterprise context"),
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory to save output")
):
    """
    Translates a document with enterprise context and back-translation verification.
    """
    input_path = Path(input_file)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        console.print(f"[bold red]Input file not found:[/bold red] {input_file}")
        raise typer.Exit(code=1)

    # Load context if provided
    context_text = ""
    if context_file:
        ctx_path = Path(context_file)
        if ctx_path.exists():
            context_text = ctx_path.read_text()
        else:
            console.print(f"[yellow]Warning: Context file {context_file} not found. Proceeding without context.[/yellow]")

    # Run async flow
    try:
        asyncio.run(run_translation_flow(input_path, target_lang, context_text, out_path))
    except Exception as e:
        console.print(f"[bold red]Error during translation flow:[/bold red] {e}")
        raise typer.Exit(code=1)

def run() -> None:
    """CLI entry point that handles manifest-aware help output."""

    if _should_emit_manifest(sys.argv):
        _print_manifest()
        return

    app()


if __name__ == "__main__":
    run()
