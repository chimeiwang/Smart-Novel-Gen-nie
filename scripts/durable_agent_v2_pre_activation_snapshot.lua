local prefix = 'inkforge:executions'
local active_key = prefix .. ':drain:active'
local pending_key = prefix .. ':callbacks:pending'
local leased_key = prefix .. ':callbacks:leased'
local rejected_key = prefix .. ':callbacks:rejected'
local quarantine_key = prefix .. ':restore:quarantine'
local maximum_keys = 256

local function fail(code)
  return cjson.encode({error = code})
end

if redis.call('EXISTS', quarantine_key) == 1 then
  return fail('pre_activation_execution_quarantine')
end

local known = {
  [active_key] = true,
  [pending_key] = true,
  [leased_key] = true,
  [rejected_key] = true,
  [prefix .. ':drain:index-version'] = true
}
local cursor = '0'
local seen_count = 0
repeat
  local page = redis.call('SCAN', cursor, 'MATCH', prefix .. ':*', 'COUNT', 128)
  cursor = page[1]
  for _, key in ipairs(page[2]) do
    seen_count = seen_count + 1
    if seen_count > maximum_keys then
      return fail('pre_activation_execution_resource_limit')
    end
    if not known[key] then
      return fail('pre_activation_execution_unknown_key')
    end
  end
until cursor == '0'

if redis.call('ZCARD', active_key) ~= 0
    or redis.call('ZCARD', pending_key) ~= 0
    or redis.call('ZCARD', leased_key) ~= 0
    or redis.call('ZCARD', rejected_key) ~= 0 then
  return fail('pre_activation_execution_not_empty')
end

local server_info = redis.call('INFO', 'server')
local redis_run_id = string.match(server_info, 'run_id:([0-9a-f]+)')
if not redis_run_id then return fail('pre_activation_execution_run_id_missing') end
local current = redis.call('TIME')
local observed_at_ms = current[1] .. string.format('%03d', math.floor(current[2] / 1000))
return cjson.encode({
  sourceVersion = '2',
  indexVersion = 'pre-activation',
  redisRunId = redis_run_id,
  observedAtMs = observed_at_ms,
  active = {},
  pending = {},
  leased = {},
  rejected = {},
  quarantined = false
})
