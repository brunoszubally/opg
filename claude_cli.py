#!/usr/bin/env python3
"""
Claude AI Terminal CLI
Használat: claude "kérdésed" vagy csak claude (interaktív mód)
"""

import os
import sys
import json
from typing import Optional

try:
    import anthropic
except ImportError:
    print("❌ Az 'anthropic' csomag nincs telepítve.")
    print("Telepítés: pip install anthropic")
    sys.exit(1)


def get_api_key() -> Optional[str]:
    """API kulcs lekérése environment változóból vagy fájlból"""
    # Először próbáljuk az environment változót
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return api_key
    
    # Ha nincs, próbáljuk a ~/.anthropic/api_key fájlt
    key_file = os.path.expanduser("~/.anthropic/api_key")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    
    return None


def chat_with_claude(prompt: str, model: str = "claude-3-5-sonnet-20241022") -> str:
    """Chat a Claude AI-val"""
    api_key = get_api_key()
    if not api_key:
        print("❌ ANTHROPIC_API_KEY nincs beállítva!")
        print("\nBeállítás:")
        print("1. Environment változó: export ANTHROPIC_API_KEY='your-key'")
        print("2. Vagy fájl: echo 'your-key' > ~/.anthropic/api_key")
        sys.exit(1)
    
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Válasz kinyerése
        if message.content:
            return message.content[0].text
        return "Nincs válasz."
    
    except Exception as e:
        return f"❌ Hiba: {str(e)}"


def interactive_mode():
    """Interaktív chat mód"""
    print("🤖 Claude AI Terminal CLI")
    print("Írj 'exit' vagy 'quit' a kilépéshez, 'clear' a beszélgetés törléséhez\n")
    
    conversation_history = []
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Viszlát! 👋")
                break
            
            if user_input.lower() == 'clear':
                conversation_history = []
                print("Beszélgetés törölve.\n")
                continue
            
            # API hívás
            api_key = get_api_key()
            if not api_key:
                print("❌ ANTHROPIC_API_KEY nincs beállítva!")
                continue
            
            try:
                client = anthropic.Anthropic(api_key=api_key)
                
                # Hozzáadjuk a felhasználó üzenetét a beszélgetéshez
                conversation_history.append({"role": "user", "content": user_input})
                
                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=conversation_history
                )
                
                if message.content:
                    response = message.content[0].text
                    print(f"\nClaude: {response}\n")
                    # Hozzáadjuk a választ is a beszélgetéshez
                    conversation_history.append({"role": "assistant", "content": response})
                else:
                    print("Nincs válasz.\n")
            
            except Exception as e:
                print(f"❌ Hiba: {str(e)}\n")
        
        except KeyboardInterrupt:
            print("\n\nViszlát! 👋")
            break
        except EOFError:
            break


def main():
    """Főprogram"""
    if len(sys.argv) > 1:
        # Egyetlen prompt argumentumként
        prompt = " ".join(sys.argv[1:])
        response = chat_with_claude(prompt)
        print(response)
    else:
        # Interaktív mód
        interactive_mode()


if __name__ == "__main__":
    main()
