local prefix = 'inkforge:runs'
local marker_key = prefix .. ':drain:index-version'
local queued_index_key = prefix .. ':drain:queued'
local running_index_key = prefix .. ':drain:running'
local ready_key = prefix .. ':ready'
local processing_key = prefix .. ':processing'
local statuses_key = prefix .. ':statuses'
local maximum_statuses = 256

local marker = redis.call('GET', marker_key)
if marker then
  if marker == '1' then return 'existing' end
  return 'invalid-version'
end
if redis.call('ZCARD', queued_index_key) ~= 0
    or redis.call('ZCARD', running_index_key) ~= 0
    or redis.call('ZCARD', ready_key) ~= 0
    or redis.call('ZCARD', processing_key) ~= 0 then
  return 'active-or-orphan-index'
end
local status_count = redis.call('HLEN', statuses_key)
if status_count > maximum_statuses then return 'status-limit' end
local statuses = redis.call('HGETALL', statuses_key)
for offset = 2, #statuses, 2 do
  local status = statuses[offset]
  if status == 'queued' or status == 'running' then
    return 'active-status-without-index'
  elseif status ~= 'completed' and status ~= 'failed' and status ~= 'cancelled' then
    return 'invalid-status'
  end
end
redis.call('SET', marker_key, '1')
return 'initialized'
