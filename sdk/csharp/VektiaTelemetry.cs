/*
 * Vektia Telemetry SDK — C# / Unity / .NET Integration
 * 
 * Kullanım:
 *   var client = new VektiaTelemetry("http://vektia-server:8000", "api-key", "server_01");
 *   await client.TrackAsync("player_123", "hit", new Vector3(100, 200, 10));
 */

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Vektia.SDK
{
    /// <summary>
    /// Vektia Telemetry Client for .NET / Unity servers.
    /// Thread-safe with automatic batch flushing.
    /// </summary>
    public class VektiaTelemetry : IDisposable
    {
        private readonly string _apiUrl;
        private readonly string _apiKey;
        private readonly string _serverId;
        private readonly int _batchSize;
        private readonly HttpClient _httpClient;
        private readonly ConcurrentQueue<TelemetryEvent> _queue;
        private readonly Timer _flushTimer;
        private bool _disposed;

        public VektiaTelemetry(
            string apiUrl,
            string apiKey,
            string serverId = "csharp_server",
            int batchSize = 10,
            int flushIntervalMs = 200)
        {
            _apiUrl = apiUrl.TrimEnd('/');
            _apiKey = apiKey;
            _serverId = serverId;
            _batchSize = batchSize;
            _queue = new ConcurrentQueue<TelemetryEvent>();

            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromSeconds(5)
            };
            _httpClient.DefaultRequestHeaders.Add("X-Vektia-Key", _apiKey);

            // Periodic flush timer
            _flushTimer = new Timer(
                async _ => await FlushAsync(),
                null,
                flushIntervalMs,
                flushIntervalMs
            );

            Console.WriteLine($"[Vektia SDK] Initialized → {_apiUrl} (server: {_serverId})");
        }

        /// <summary>
        /// Track a telemetry event (thread-safe).
        /// </summary>
        public void Track(string playerId, string actionType, float x = 0, float y = 0, float z = 0)
        {
            var evt = new TelemetryEvent
            {
                player_id = playerId,
                action_type = actionType,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                server_id = _serverId,
                coords = new Coords { x = x, y = y, z = z }
            };

            _queue.Enqueue(evt);

            if (_queue.Count >= _batchSize)
            {
                _ = FlushAsync(); // Fire and forget
            }
        }

        /// <summary>
        /// Async version of Track.
        /// </summary>
        public async Task TrackAsync(string playerId, string actionType, float x = 0, float y = 0, float z = 0)
        {
            Track(playerId, actionType, x, y, z);

            if (_queue.Count >= _batchSize)
            {
                await FlushAsync();
            }
        }

        /// <summary>
        /// Flush all queued events to the Vektia API.
        /// </summary>
        public async Task FlushAsync()
        {
            if (_queue.IsEmpty) return;

            var events = new List<TelemetryEvent>();
            while (_queue.TryDequeue(out var evt) && events.Count < _batchSize * 2)
            {
                events.Add(evt);
            }

            if (events.Count == 0) return;

            var batch = new
            {
                events = events,
                server_id = _serverId
            };

            try
            {
                var json = JsonSerializer.Serialize(batch);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var response = await _httpClient.PostAsync($"{_apiUrl}/api/v1/telemetry/batch", content);

                if (!response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"[Vektia SDK] HTTP Error: {response.StatusCode}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Vektia SDK] Flush error: {ex.Message}");
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            _flushTimer?.Dispose();
            FlushAsync().GetAwaiter().GetResult(); // Final flush
            _httpClient?.Dispose();
        }

        // === Data Models ===

        private class TelemetryEvent
        {
            public string player_id { get; set; }
            public string action_type { get; set; }
            public long timestamp { get; set; }
            public string server_id { get; set; }
            public Coords coords { get; set; }
        }

        private class Coords
        {
            public float x { get; set; }
            public float y { get; set; }
            public float z { get; set; }
        }
    }
}
