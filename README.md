# 🎬 Professional Video Merger Bot

An advanced Telegram bot for merging multiple videos with  
professional features, MongoDB integration, and beautiful UI.

***

## ✨ Features

### 🚀 Core Features
- **Ultra-Fast Video Merging** – Smart algorithm for instant compatible video merging  
- **Multi-Format Support** – MP4, MKV, AVI, WebM, and more  
- **Professional UI** – Beautiful inline keyboards and progress tracking  
- **Multiple Upload Options** – Telegram upload or GoFile.io hosting  

### 🛡️ Advanced Features
- **MongoDB Integration** – Complete user management and analytics  
- **Force Subscribe** – Mandatory channel subscription system  
- **Admin Panel** – Comprehensive bot management tools  
- **Broadcast System** – Send messages to all users  
- **Authorization System** – Control access for groups and chats  
- **Activity Logging** – Track all merge activities and new users  

### 📊 Analytics & Management
- **User Statistics** – Track total users, daily activity, merge counts  
- **Merge Logging** – Complete merge history with file details  
- **Admin Controls** – Ban/unban users, manage authorized chats  
- **Real-time Stats** – Live bot performance monitoring  

***

## 🔧 Setup & Installation

### Prerequisites
- Python 3.8+  
- FFmpeg installed  
- MongoDB database (local or Atlas)  
- Telegram Bot Token from @BotFather  

### Environment Variables  
Create a `.env` file or set these environment variables:
```
# Telegram Bot Configuration
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token

# MongoDB Configuration
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=video_merger_bot

# Channel & Group Settings (Optional)
FORCE_SUB_CHANNEL=@your_channel
UPDATE_CHANNEL=@your_updates_channel
SUPPORT_GROUP=@your_support_group

# Admin Configuration
OWNER_ID=your_user_id
ADMINS=user_id1,user_id2

# Logging Channels (Optional)
LOG_CHANNEL=channel_id_for_new_users
MERGE_LOG_CHANNEL=channel_id_for_merge_logs

# File Storage (Optional)
DOWNLOAD_DIR=downloads
GOFILE_TOKEN=your_gofile_token

# Bot Customization (Optional)
BOT_NAME=Video Merger Bot
BOT_USERNAME=your_bot_username
DEVELOPER=Your Name
```

### Installation Steps
1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/video-merger-bot
   cd video-merger-bot
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```
4. **Install FFmpeg:**
   - **Ubuntu/Debian:** `sudo apt install ffmpeg`
   - **Windows:** Download from ffmpeg.org and add to PATH  
   - **macOS:** `brew install ffmpeg`
5. **Start Bot:**
   ```bash
   python bot_enhanced.py
   ```

***

## 🐳 Docker Deployment

### Docker Compose
```yaml
version: '3.8'
services:
  bot:
    build: .
    environment:
      - API_ID=${API_ID}
      - API_HASH=${API_HASH}
      - BOT_TOKEN=${BOT_TOKEN}
      - MONGO_URI=mongodb://mongo:27017
      - DATABASE_NAME=video_merger_bot
      - OWNER_ID=${OWNER_ID}
      - FORCE_SUB_CHANNEL=${FORCE_SUB_CHANNEL}
    volumes:
      - ./downloads:/app/downloads
    depends_on:
      - mongo
    restart: unless-stopped

  mongo:
    image: mongo:6.0
    volumes:
      - mongodb_data:/data/db
    restart: unless-stopped

volumes:
  mongodb_data:
```
```bash
docker-compose up -d
```

### Dockerfile Only
```bash
docker build -t video-merger-bot .
docker run -d \
  -e API_ID=... \
  -e API_HASH=... \
  -e BOT_TOKEN=... \
  -e MONGO_URI=... \
  -e OWNER_ID=... \
  -v ./downloads:/app/downloads \
  video-merger-bot
```

***

## ☁️ Cloud Deployment

### Heroku
1. Create a new Heroku app  
2. Set Config Vars from your environment  
3. Add buildpacks:
   - `heroku/python`
   - `https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git`  
4. Deploy from GitHub  

### Railway / Render
- Connect repo, set environment variables, deploy automatically  

***

## 🎯 Usage Guide

### For Users
1. Send `/start`  
2. Join required channel if prompted  
3. Upload videos or send download links  
4. Click **🎬 Merge Now**  
5. Choose **Telegram** or **GoFile**  
6. Receive merged file  

### Admin Commands
- `/admin` – Access panel  
- `/stats` – View stats  
- `/broadcast` – Broadcast message  
- `/cancel` – Cancel operation  

### Admin Panel
- **📊 Bot Stats**  
- **👥 User Management**  
- **📢 Broadcast**  
- **🔧 Settings**  
- **💬 Authorized Chats**  
- **📋 Logs**  

***

## 📱 Bot Commands

| Command         | Description                          | Access         |
|-----------------|--------------------------------------|----------------|
| `/start`        | Welcome & main menu                  | All users      |
| `/help`         | How to use                           | All users      |
| `/cancel`       | Cancel current operation             | All users      |
| `/merge`        | Start merge process                  | All users      |
| `/stats`        | Bot statistics                       | Admins         |
| `/admin`        | Admin panel                          | Admins         |
| `/broadcast`    | Broadcast message                    | Owner only     |

***

## 🔧 Configuration

### Force Subscribe
1. Create channel & add bot as admin  
2. Set `FORCE_SUB_CHANNEL`  
3. Users must join to use bot  

### Admin Setup
1. Obtain your user ID  
2. Set `OWNER_ID` and `ADMINS`  

### Logging Setup
1. Create logging channels  
2. Set `LOG_CHANNEL` and `MERGE_LOG_CHANNEL`  

***

## 🔍 Monitoring & Analytics

- **users** collection – user data  
- **authorized_chats** – allowed chats  
- **merge_logs** – merge history  
- **broadcast_logs** – broadcasts  

***

## 🛠️ Project Structure

```
├── bot_enhanced.py
├── config.py
├── database.py
├── helpers.py
├── downloader.py
├── merger.py
├── uploader.py
├── utils.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

***

## 🤝 Contributing

1. Fork repo  
2. Create feature branch  
3. Commit & test  
4. Open pull request  

***

## 📄 License

Licensed under MIT License. See LICENSE.

***

## 🤝 Support

- **Updates:** @your_update_channel  
- **Support Group:** @your_support_group  
- **Developer:** @your_username

***

Made with ❤️ by **Your Name**
