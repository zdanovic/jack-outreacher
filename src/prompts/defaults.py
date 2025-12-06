# ------------------- DEVICE PROFILES -------------------
DEVICE_PROFILES = [
    # === iOS ===
    {"device_model": "iPhone 15 Pro", "system_version": "17.4.1", "app_version": "10.11.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 14 Pro Max", "system_version": "17.3.1", "app_version": "10.10.1", "lang_code": "en", "system_lang_code": "en-GB"},
    {"device_model": "iPhone 13", "system_version": "17.2.1", "app_version": "10.9.2", "lang_code": "de", "system_lang_code": "de-DE"},
    {"device_model": "iPhone 12 Mini", "system_version": "16.7.5", "app_version": "10.7.0", "lang_code": "es", "system_lang_code": "es-ES"},
    {"device_model": "iPhone SE (3rd generation)", "system_version": "17.0.3", "app_version": "10.10.0", "lang_code": "fr", "system_lang_code": "fr-FR"},
    {"device_model": "iPad Pro (12.9-inch) (6th generation)", "system_version": "17.4.0", "app_version": "10.11.0", "lang_code": "en", "system_lang_code": "en-CA"}, # iPadOS
    {"device_model": "iPhone 15", "system_version": "17.4.1", "app_version": "10.11.1", "lang_code": "ru", "system_lang_code": "ru-RU"},
    {"device_model": "iPhone 14 Plus", "system_version": "17.3.0", "app_version": "10.10.0", "lang_code": "it", "system_lang_code": "it-IT"},

    # === Android ===
    {"device_model": "Pixel 8 Pro", "system_version": "14", "app_version": "10.10.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Samsung SM-S918B", "system_version": "14", "app_version": "10.9.1", "lang_code": "en", "system_lang_code": "en-GB"}, # Galaxy S23 Ultra
    {"device_model": "Pixel 7a", "system_version": "14", "app_version": "10.10.0", "lang_code": "en", "system_lang_code": "en-AU"},
    {"device_model": "Samsung SM-G991B", "system_version": "13", "app_version": "10.8.0", "lang_code": "de", "system_lang_code": "de-DE"}, # Galaxy S21
    {"device_model": "Xiaomi 2201116SG", "system_version": "13", "app_version": "10.7.5", "lang_code": "es", "system_lang_code": "es-ES"}, # Xiaomi 12 Pro
    {"device_model": "OnePlus 11", "system_version": "14", "app_version": "10.9.0", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Samsung SM-A546B", "system_version": "14", "app_version": "10.10.1", "lang_code": "ru", "system_lang_code": "ru-RU"}, # Galaxy A54

    # === Desktop ===
    {"device_model": "PC 64bit", "system_version": "Windows 11", "app_version": "5.1.1", "lang_code": "en", "system_lang_code": "en-US"}, # Telegram Desktop Windows
    {"device_model": "MacBookPro18,1", "system_version": "macOS 14.4.1", "app_version": "10.11.0", "lang_code": "en", "system_lang_code": "en-US"}, # Telegram macOS (native)
    {"device_model": "PC 64bit", "system_version": "Ubuntu 22.04", "app_version": "5.1.0", "lang_code": "en", "system_lang_code": "en-GB"}, # Telegram Desktop Linux
    {"device_model": "iMac21,1", "system_version": "macOS 13.6", "app_version": "5.0.1", "lang_code": "de", "system_lang_code": "de-DE"}, # Telegram Desktop macOS
    {"device_model": "PC 64bit", "system_version": "Windows 10", "app_version": "4.16.9", "lang_code": "ru", "system_lang_code": "ru-RU"}, # Slightly older Win/TDesktop version

    # You can add more language and version variations
]

# --- Default Channels (Greatly Expanded) ---
DEFAULT_CHANNELS = [
    # Official / Platform / Telegram
    "telegram", "durov", "TelegramTips", "TelegramContests", "telegramdesktoptips",
    "telegramandroid", "telegramios", "TelegramThemes", "TelegramStickers", "BetaTesting",

    # Major International News / Media
    "bbcnews", "bbcworld", "nytimes", "cnn", "Reuters", "APNews", "financialtimes",
    "wsj", "guardian", "guardiannews", "forbes", "bloomberg", "theeconomist",
    "washingtonpost", "time", "abcnews", "nbcnews", "cbsnews", "skynews",
    "aljazeeraenglish", "euronews", "france24_en", "dwnews", "rtenews",

    # Technology / Development / Science
    "techcrunch", "theverge", "wired", "arstechnica", "thenextweb", "engadget",
    "hackernews", "producthunt", "github", "gitlab", "stack_overflow", "medium_tech",
    "openai", "googleai", "deepmind", "metaai", "nvidia", "intel", "microsoft",
    "awscloud", "googlecloud", "azure", "kubernetesio", "docker", "python", "javascript",
    "golang", "rustlang", "cplusplusnews", "datascience", "machinelearning",
    "ai_research", "ai_news", "bigdata", "cloudcomputing", "devops", "backend",
    "frontend", "mobiledev", "iosdev", "androiddev", "security", "infosec",
    "cybersecurity", "bugbounty", "netsec",

    # Science / Space / Education
    "nasa", "spacex", "esa", "astro_physics", "astronomy", "space", "natgeoscience",
    "science", "newscientist", "popsci", "iflscience", "chemistry", "physics",
    "biology", "neuroscience", "mit_news", "stanford", "harvard", "berkeley",
    "coursera", "edx", "khanacademy", "udemy", "udacity", "skillshare", "masterclass",
    "ted_talks", "howstuffworks",

    # Business / Finance / Economics
    "harvardbiz", "incmagazine", "fastcompany", "entrepreneur", "marketwatch",
    "investing", "bloombergbusiness", "businessinsider", "economist", "financialmarkets",
    "startups", "venturecapital", "fintech", "saas", "productmanagement",

    # Entertainment / Memes / Culture
    "9gag", "memes", "dankmemes", "wholesomememes", "funny", "jokes",
    "movies", "cinema", "film_community", "netflixfans", "hbomax", "disneyplus_news",
    "primevideoupdates", "imdb_updates", "rottentomatoes", "music", "spotifynews",
    "applemusicnews", "soundcloudcommunity", "gaming", "ign", "gamespot", "twitch",
    "steamcommunity", "playstation", "xbox", "nintendo",

    # Lifestyle / Hobbies / Art / Education
    "natgeo", "discovery", "history", "archaeology", "art", "painting", "photography",
    "architecture", "design", "minimalism", "travel", "worldtravel", "food", "cooking",
    "recipes", "fitness", "health", "meditation", "yoga", "psychology", "philosophy",
    "books", "literature", "poetry", "writing", "learnenglish", "languages", "duolingo",
    "diy", "lifehacks", "comics", "anime", "manga", "boardgames", "chess", "sports",
    "soccer", "basketball", "f1", "nfl", "mlb", "nhl", "olympics", "fashion",
    "interiordesign", "gardening", "pets", "dogs", "cats", "dailyart", "bookclub",

    # Regional / Other Languages
    # Russian / Eastern Europe
    "vc_ru", "meduzalive", "tass_agency", "kommersant", "rbc_news",
    # German
    "tagesschau", "derspiegel", "zeitonline", "faznet",
    # French
    "lemondefr", "franceinfo", "lesechos",
    # Spanish
    "elpais", "elmundo", "abc_es", "lavanguardia",
    # Italian
    "repubblica", "corriere", "ilsole24ore",
    # Portuguese (Brazil / PT)
    "globo_news", "folha", "publico_pt",
    # Arabic
    "ajarabic", "bbcarabic", "aljazeeranet",
    # Chinese
    "xhnews", "china_daily",
    # Indian
    "indiatimes", "thehindu", "indianexpress",
    # Japanese
    "japantimes", "nhk_world",
    # Korean
    "koreatimes", "yonhapnews",

    # City / Local
    "berlin_live", "london", "nyc", "tokyo_news", "paris", "moscow", "milan",
    "barcelona", "sydney", "toronto", "singapore",
]

# --- Default Users or Bots (Greatly Expanded) ---
DEFAULT_USERS_OR_BOTS = [
    # Official Telegram bots
    "BotFather", "SpamBot", "DiscussBot", "vote", "sticker", "GmailBot", "IFTTT",
    "TelegramAuditions", "VerifyBot", "GDPRbot", "Stickers", "QuizBot", "PollBot",

    # Useful / Popular Bots (Functionality varies, mostly utilities)
    "wiki", "imdb", "vid", "music", "pic", "gif", "bing", "duckduckbot",
    "temp_mail_bot", "DropMailBot", "fakemailbot",
    "voicybot", "recognizebot",
    "GitHubBot", "GitLabBot", "travis_ci_bot", "jenkins_bot",
    "SkeddyBot", "AlertBot", "RemindMeBot",
    "FeedReaderBot", "TheFeedReaderBot",
    "GameBot", "Gamee", "inlinegamesbot",
    "ConverterBot", "OfficeConverterBot",
    "TranslateBot", "YTranslateBot", "GoogleTranslateBot",
    "URLShortenerBot", "QRCodeBot",
    "CryptoBot", "TracktxBot",
    "AirTrackBot",
    "WeatherBot",
    "LikeBot",
    "ControllerBot",
    "LivegramBot",
    "GetPublicLinkBot",
    "FileConverterBot",
    "JsonDumpBot",
    "SilentMessageBot",

    # Additional utility / info bots
    "NewsBot", "ChannelBot", "CommentsBot", "gifbot", "picbot", "voicetotextbot",
    "unitconverterbot", "CurrencyRateBot", "translator_bot", "pingbot",

    # Well-known users / brands (mainly for reading public channels)
    "durov",
    "elonmusk",
    "BillGates",
    "BarackObama",
    "Wikipedia",
    "InternetArchive",
    "creativecommons",
    "fsf",
    "eff",
    "neuralink",
]
