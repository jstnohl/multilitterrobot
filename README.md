# litterbot

## Description

An app to interact with the "Litter Robot", by [Whisker](https://www.litter-robot.com/litter-robot-4.html).

Original Code from projects located at: 

1. pylitterbot (the Python library)

[github.com/natekspencer/pylitterbot](https://github.com/natekspencer/pylitterbot)

2. litterbot (FastAPI + SvelteKit) 

[github.com/engageintellect/litterbot](https://github.com/engageintellect/litterbot)
    (This one is explicitly a FastAPI backend wrapper around pylitterbot)

Thanks guys for making some awesome stuff! 

Configuration

This project expects a .env file in the project root with your Litter-Robot credentials.Create it with:

Bash

nano .env

Paste the following and fill in your details:
Properties

LITTER_EMAIL=your@email.com
LITTER_PASSWORD=yourpassword

Save and exit (Ctrl+O, Enter, Ctrl+X).Then make sure the file is only readable by root (recommended):Bashchmod 600 .env


[![Kitty Crapper](kitty-crapper.png)](https://litterbot.vercel.app)

This app uses Python and FastAPI (with Web Sockets) as a backend wrapper around [@natekspencer](https://github.com/natekspencer)'s [pylitterbot](https://github.com/natekspencer/pylitterbot) library. The frontend is built using [SvelteKit](https://kit.svelte.dev/), [TailwindCSS](https://tailwindcss.com), and [DaisyUI](https://daisyui.com).

Inspired by [@natekspencer](https://github.com/natekspencer)'s [pylitterbot](https://github.com/natekspencer/pylitterbot).

## Getting Started

Clone and navigate to the the repository.

```bash
git clone https://engageintellect/litterbot
cd litterbot
```

### Configure environment variables.

```bash
cp /server/.env.example /server/.env
```

**Note:** You will need to get your Litter Robot's username and password credentials from the Whisker app.

```bash
cp /client/.env.example /client/.env
```

**Note:** Be sure to update the example values with your own.

### Server

Configure and run backend.

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Client

Configure and run client.

```bash
cd client
pnpm i
pnpm run dev --host
```
