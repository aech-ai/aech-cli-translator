import typer
import os
from pathlib import Path
from typing import Optional
from litellm import completion
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

app = typer.Typer()
console = Console()

def call_llm(prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
    """Helper to call LLM via litellm."""
    # Use AECH_LLM_MODEL if set, otherwise default to gpt-4o or similar
    model = os.getenv("AECH_LLM_MODEL", "gpt-4o")
    # If model is "openai:gpt-4o", litellm handles it.
    
    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        console.print(f"[bold red]Error calling LLM:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command()
def translate(
    input_file: str,
    target_lang: str,
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

    source_text = input_path.read_text()
    
    # Load context if provided
    context_text = ""
    if context_file:
        ctx_path = Path(context_file)
        if ctx_path.exists():
            context_text = ctx_path.read_text()
        else:
            console.print(f"[yellow]Warning: Context file {context_file} not found. Proceeding without context.[/yellow]")

    # 1. Translate
    console.print(f"[blue]Translating {input_file.name} to {target_lang}...[/blue]")
    translation_system_prompt = f"""
    You are an expert enterprise translator.
    Target Language: {target_lang}
    
    Enterprise Context:
    {context_text}
    
    Instructions:
    - Translate the content accurately, preserving formatting (Markdown).
    - Use the provided Enterprise Context to ensure correct terminology.
    - Do not add conversational filler. Output ONLY the translated markdown.
    """
    
    translated_text = call_llm(source_text, system_prompt=translation_system_prompt)
    
    # Save translation
    translated_filename = f"{input_path.stem}_{target_lang}.md"
    translated_file = out_path / translated_filename
    translated_file.write_text(translated_text)
    console.print(f"[green]Translation saved to {translated_file}[/green]")

    # 2. Back-Translate
    console.print(f"[blue]Back-translating for verification...[/blue]")
    back_translation_system_prompt = f"""
    You are an expert translator.
    Translate the following {target_lang} text back to the original language (English/Source).
    Output ONLY the translated markdown.
    """
    back_translated_text = call_llm(translated_text, system_prompt=back_translation_system_prompt)

    # 3. Verify / Generate Report
    console.print(f"[blue]Generating Quality Report...[/blue]")
    report_system_prompt = """
    You are a Translation Quality Assurance Auditor.
    Compare the Original Text and the Back-Translated Text.
    Identify any significant discrepancies in meaning, tone, or terminology.
    Ignore minor phrasing differences if the meaning is preserved.
    
    Output a Markdown report with:
    - Overall Quality Assessment (Pass/Fail/Needs Review)
    - Key Discrepancies (if any)
    - Recommendations
    """
    
    report_prompt = f"""
    Original Text:
    {source_text}
    
    Back-Translated Text:
    {back_translated_text}
    """
    
    report_text = call_llm(report_prompt, system_prompt=report_system_prompt)
    
    # Save report
    report_filename = f"{input_path.stem}_translation_report.md"
    report_file = out_path / report_filename
    report_file.write_text(report_text)
    console.print(f"[green]Report saved to {report_file}[/green]")
    
    import json
    print(json.dumps({
        "translated_file": str(translated_file),
        "report_file": str(report_file)
    }))

if __name__ == "__main__":
    app()
