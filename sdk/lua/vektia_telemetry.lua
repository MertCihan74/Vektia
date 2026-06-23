--[[
    Vektia Telemetry SDK — FiveM (GTA 5) Lua Integration
    
    Bu script FiveM sunucusuna resource olarak eklenir.
    Oyuncu eylemlerini non-blocking olarak Vektia API'sine gönderir.
    
    KURULUM:
    1. Bu dosyayı sunucunuzun resources klasörüne kopyalayın
    2. fxmanifest.lua ile resource olarak tanımlayın
    3. server.cfg'ye: ensure vektia_telemetry
    4. config bölümündeki VEKTIA_API_URL ve VEKTIA_API_KEY değerlerini ayarlayın
]]

-- ============================================
-- KONFİGÜRASYON
-- ============================================
local Config = {
    -- Vektia API sunucu adresi
    API_URL = "http://YOUR_VEKTIA_SERVER:8000",
    
    -- API Anahtarı (Vektia panelinden alınır)
    API_KEY = "YOUR_API_KEY_HERE",
    
    -- Veri gönderim ayarları
    BATCH_SIZE = 10,        -- Kaç olay birikince toplu gönderilsin
    BATCH_INTERVAL = 100,   -- Maksimum bekleme süresi (ms)
    
    -- Hangi olaylar izlensin
    TRACK_HITS = true,      -- Silah/yumruk vuruşları
    TRACK_MOVEMENT = true,  -- Hareket (her 2 saniyede bir)
    TRACK_TRADES = true,    -- Ticaret/etkileşim
    
    -- Sunucu kimliği
    SERVER_ID = "fivem_srv_01",
    
    -- Debug modu
    DEBUG = false,
}

-- ============================================
-- OLAY KUYRUĞU
-- ============================================
local eventQueue = {}
local lastFlush = GetGameTimer()

--- Telemetri olayı oluştur ve kuyruğa ekle
--- @param playerId string Oyuncu sunucu ID'si
--- @param actionType string Eylem türü (hit, click, move, trade, interact)
--- @param coords table|nil {x, y, z} koordinatları
local function queueEvent(playerId, actionType, coords)
    local event = {
        player_id = tostring(playerId),
        action_type = actionType,
        timestamp = GetGameTimer() * 1.0, -- Milisaniye
        server_id = Config.SERVER_ID,
    }
    
    if coords then
        event.coords = {
            x = math.floor(coords.x * 100) / 100,
            y = math.floor(coords.y * 100) / 100,
            z = math.floor(coords.z * 100) / 100,
        }
    end
    
    table.insert(eventQueue, event)
    
    -- Batch dolunca veya süre geçince gönder
    if #eventQueue >= Config.BATCH_SIZE then
        flushEvents()
    end
end

--- Kuyruktaki olayları toplu olarak Vektia API'sine gönderir
function flushEvents()
    if #eventQueue == 0 then return end
    
    local batch = {
        events = eventQueue,
        server_id = Config.SERVER_ID,
    }
    
    -- Kuyruğu temizle (gönderim başarısız olsa bile — non-blocking)
    eventQueue = {}
    lastFlush = GetGameTimer()
    
    -- Non-blocking HTTP POST
    PerformHttpRequest(
        Config.API_URL .. "/api/v1/telemetry/batch",
        function(statusCode, responseText, headers)
            if Config.DEBUG then
                if statusCode == 200 then
                    print("[Vektia] Batch gönderildi: " .. #batch.events .. " olay")
                else
                    print("[Vektia] HATA: HTTP " .. tostring(statusCode))
                end
            end
        end,
        "POST",
        json.encode(batch),
        {
            ["Content-Type"] = "application/json",
            ["X-Vektia-Key"] = Config.API_KEY,
        }
    )
end

-- ============================================
-- FiveM OLAY DİNLEYİCİLER (Sunucu Tarafı)
-- ============================================

-- Silah ateşleme / vuruş olayı
if Config.TRACK_HITS then
    RegisterNetEvent("weaponDamageEvent")
    AddEventHandler("weaponDamageEvent", function(sender, data)
        local ped = GetPlayerPed(sender)
        local coords = GetEntityCoords(ped)
        queueEvent(
            GetPlayerIdentifier(sender, 0) or sender,
            "hit",
            coords
        )
    end)
end

-- Oyuncu hareket takibi (periyodik)
if Config.TRACK_MOVEMENT then
    CreateThread(function()
        while true do
            Wait(2000) -- Her 2 saniyede bir
            
            local players = GetPlayers()
            for _, playerId in ipairs(players) do
                local ped = GetPlayerPed(playerId)
                if ped and DoesEntityExist(ped) then
                    local coords = GetEntityCoords(ped)
                    local identifier = GetPlayerIdentifier(playerId, 0) or playerId
                    queueEvent(identifier, "move", coords)
                end
            end
        end
    end)
end

-- Periyodik flush (batch dolmasa bile)
CreateThread(function()
    while true do
        Wait(Config.BATCH_INTERVAL)
        
        if #eventQueue > 0 and (GetGameTimer() - lastFlush) >= Config.BATCH_INTERVAL then
            flushEvents()
        end
    end
end)

-- ============================================
-- EXPORT (Diğer resource'lar bu fonksiyonu çağırabilir)
-- ============================================

-- Örnek: exports.vektia_telemetry:trackEvent(playerId, "trade", {x=100, y=200, z=10})
exports("trackEvent", function(playerId, actionType, coords)
    queueEvent(playerId, actionType, coords)
end)

-- Başlangıç bildirimi
print("========================================")
print("  [Vektia] Telemetry SDK Aktif")
print("  API: " .. Config.API_URL)
print("  Server: " .. Config.SERVER_ID)
print("========================================")
