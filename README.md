# README.md - Enhanced Video Merger Bot Documentation

# 🎬 Professional Video Merger Bot

An advanced Telegram bot for merging multiple videos with professional features, MongoDB integration, and beautiful UI.

## ✨ Features

### 🚀 Core Features
- **Ultra-Fast Video Merging** - Smart algorithm for instant compatible video merging
- **Multi-Format Support** - MP4, MKV, AVI, WebM, and more
- **Professional UI** - Beautiful inline keyboards and progress tracking
- **Multiple Upload Options** - Telegram upload or GoFile.io hosting

### 🛡️ Advanced Features
- **MongoDB Integration** - Complete user management and analytics
- **Force Subscribe** - Mandatory channel subscription system
- **Admin Panel** - Comprehensive bot management tools
- **Broadcast System** - Send messages to all users
- **Authorization System** - Control access for groups and chats
- **Activity Logging** - Track all merge activities and new users

### 📊 Analytics & Management
- **User Statistics** - Track total users, daily activity, merge counts
- **Merge Logging** - Complete merge history with file details
- **Admin Controls** - Ban/unban users, manage authorized chats
- **Real-time Stats** - Live bot performance monitoring

## 🔧 Setup & Installation

### Prerequisites
- Python 3.8+
- FFmpeg installed
- MongoDB database (local or MongoDB Atlas)
- Telegram Bot Token from @BotFather

### Environment Variables

Create a `.env` file or set these environment variables:

```env
# Required - Telegram Bot Configuration
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token

# Required - MongoDB Configuration
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=video_merger_bot

# Optional - Channel & Group Settings
FORCE_SUB_CHANNEL=@your_channel  # Channel username or ID
UPDATE_CHANNEL=your_updates_channel
SUPPORT_GROUP=your_support_group

# Required - Admin Configuration
OWNER_ID=your_user_id
ADMINS=user_id1,user_id2,user_id3

# Optional - Logging Channels
LOG_CHANNEL=channel_id_for_new_users
MERGE_LOG_CHANNEL=channel_id_for_merge_logs

# Optional - File Storage
DOWNLOAD_DIR=downloads
GOFILE_TOKEN=your_gofile_token

# Optional - Bot Customization
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

3. **Set up environment variables:**
```bash
cp .env.example .env
# Edit .env with your values
```

4. **Install FFmpeg:**

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
- Download from https://ffmpeg.org/download.html
- Add to system PATH

**macOS:**
```bash
brew install ffmpeg
```

5. **Set up MongoDB:**

**Local MongoDB:**
```bash
# Install MongoDB Community Edition
# Start MongoDB service
mongod
```

**MongoDB Atlas (Cloud):**
- Create account at https://cloud.mongodb.com
- Create cluster and get connection string
- Use connection string in MONGO_URI

6. **Run the bot:**
```bash
python bot_enhanced.py
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```yaml
# docker-compose.yml
version: '3.8'

services:
  video-merger-bot:
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

**Deploy with Docker Compose:**
```bash
docker-compose up -d
```

### Using Dockerfile Only

```bash
docker build -t video-merger-bot .
docker run -d --name video-merger-bot \
  -e API_ID=your_api_id \
  -e API_HASH=your_api_hash \
  -e BOT_TOKEN=your_bot_token \
  -e MONGO_URI=your_mongo_uri \
  -e OWNER_ID=your_user_id \
  video-merger-bot
```

## ☁️ Cloud Deployment

### Heroku
1. Create new Heroku app
2. Set Config Vars (environment variables)
3. Connect GitHub repository
4. Deploy from main branch

**Required Buildpacks:**
- `heroku/python`
- `https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git`

### Railway
1. Connect GitHub repository
2. Set environment variables
3. Deploy automatically

### Render
1. Create new Web Service
2. Connect GitHub repository  
3. Set environment variables
4. Deploy

## 🎯 Usage Guide

### For Users

1. **Start the bot:** Send `/start` to get welcome message
2. **Join required channel:** If force subscribe is enabled
3. **Send videos:** Upload videos or send direct download links
4. **Merge videos:** Click "🎬 Merge Now" when ready
5. **Choose upload:** Select Telegram upload or GoFile hosting
6. **Get result:** Download your merged video

### Admin Commands

- `/admin` - Access admin panel
- `/stats` - View bot statistics  
- `/broadcast` - Send message to all users
- `/cancel` - Cancel current operation

### Admin Panel Functions

- **📊 Bot Stats** - View detailed statistics
- **👥 User Management** - Ban/unban users
- **📢 Broadcast** - Send announcements
- **🔧 Settings** - Configure bot settings
- **💬 Authorized Chats** - Manage group access
- **📋 Logs** - View activity logs

## 📱 Bot Commands

| Command | Description | Access |
|---------|-------------|---------|
| `/start` | Welcome message and main menu | All Users |
| `/help` | Usage instructions | All Users |
| `/cancel` | Cancel current operation | All Users |
| `/merge` | Start merge process | All Users |
| `/stats` | View bot statistics | Admins Only |
| `/admin` | Access admin panel | Admins Only |
| `/broadcast` | Broadcast message | Owner Only |

## 🔧 Configuration

### Force Subscribe Setup
1. Create a Telegram channel
2. Add your bot as admin to the channel
3. Set `FORCE_SUB_CHANNEL` to channel username or ID
4. Users must join channel to use bot

### Admin Setup
1. Get your Telegram user ID (use @userinfobot)
2. Set `OWNER_ID` to your user ID
3. Add other admin IDs to `ADMINS` (comma-separated)

### Logging Setup
1. Create channels for logging
2. Add bot as admin to logging channels
3. Set `LOG_CHANNEL` and `MERGE_LOG_CHANNEL` IDs

## 🔍 Monitoring & Analytics

### Database Collections
- **users** - User information and statistics
- **authorized_chats** - Authorized groups/chats
- **merge_logs** - Merge activity history
- **broadcast_logs** - Broadcast message logs

### Statistics Available
- Total users and daily growth
- Merge activity and success rates
- User engagement metrics
- System performance data

## 🛠️ Development

### Project Structure
```
video-merger-bot/
├── bot_enhanced.py          # Main bot file
├── config.py               # Configuration management
├── database.py             # MongoDB operations
├── helpers.py              # Helper functions
├── downloader.py           # File download handlers
├── merger.py               # Video merging logic
├── uploader.py             # Upload handlers
├── utils.py                # Utility functions
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker configuration  
├── docker-compose.yml     # Docker Compose setup
└── README.md              # Documentation
```

### Contributing
1. Fork the repository
2. Create feature branch
3. Make changes and test
4. Submit pull request

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🤝 Support

- **Updates:** @your_update_channel
- **Support Group:** @your_support_group  
- **Developer:** @your_username

## 🙏 Acknowledgments

- [Pyrogram](https://pyrogram.org/) - Telegram bot framework
- [FFmpeg](https://ffmpeg.org/) - Video processing engine
- [MongoDB](https://www.mongodb.com/) - Database solution

---

Made with ❤️ by [Your Name]
