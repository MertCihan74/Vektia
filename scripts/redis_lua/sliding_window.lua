--[[
    Vektia Sliding Window — Redis Lua Script
    
    Atomik olarak çalışır:
    1. Yeni timestamp'i listenin başına ekler (LPUSH)
    2. Listeyi MAX_WINDOW boyutuna kırpar (LTRIM) — RAM koruma
    3. İnaktif oyuncular için TTL ayarlar (EXPIRE)
    4. Tüm listeyi döndürür (LRANGE)
    
    KEYS[1] = player:{player_id}:clicks:{action_type}
    ARGV[1] = timestamp (milisaniye)
    ARGV[2] = max_window (örn: 20)
    ARGV[3] = ttl_seconds (örn: 300)
    
    Dönüş: Son N timestamp listesi (string olarak)
]]

local key = KEYS[1]
local timestamp = ARGV[1]
local max_window = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

-- 1. Yeni veriyi listenin başına ekle
redis.call('LPUSH', key, timestamp)

-- 2. Listeyi max_window boyutunda tut (eski veriler anında yok edilir)
redis.call('LTRIM', key, 0, max_window - 1)

-- 3. İnaktif oyuncu verilerini otomatik temizle
redis.call('EXPIRE', key, ttl)

-- 4. Mevcut listeyi döndür
return redis.call('LRANGE', key, 0, -1)
