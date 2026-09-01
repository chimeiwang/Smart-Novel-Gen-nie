local prefix = 'inkforge:runs'
local ready_key = prefix .. ':ready'
local processing_key = prefix .. ':processing'
local statuses_key = prefix .. ':statuses'
local maximum_active = 256

local function fail(code)
  return cjson.encode({error = code})
end

local queued_count = redis.call('ZCARD', ready_key)
local running_count = redis.call('ZCARD', processing_key)
local status_count = redis.call('HLEN', statuses_key)
if queued_count + running_count > maximum_active or status_count > maximum_active then
  return fail('pre_activation_v1_resource_limit')
end

local seen = {}
local function entries(queue_key, other_key, expected_status)
  local result = {}
  local values = redis.call('ZRANGE', queue_key, 0, -1, 'WITHSCORES')
  for offset = 1, #values, 2 do
    local job_id = values[offset]
    local created_ms = values[offset + 1]
    if seen[job_id] then return nil, 'pre_activation_v1_duplicate' end
    seen[job_id] = true
    if not string.match(created_ms, '^%d+$')
        or redis.call('HGET', statuses_key, job_id) ~= expected_status
        or redis.call('ZSCORE', other_key, job_id) then
      return nil, 'pre_activation_v1_binding_invalid'
    end
    table.insert(result, {id = job_id, createdAtMs = created_ms})
  end
  return result, nil
end

local queued, queued_error = entries(ready_key, processing_key, 'queued')
if queued_error then return fail(queued_error) end
local running, running_error = entries(processing_key, ready_key, 'running')
if running_error then return fail(running_error) end

local statuses = redis.call('HGETALL', statuses_key)
for offset = 2, #statuses, 2 do
  local status = statuses[offset]
  if status == 'queued' or status == 'running' then
    if not seen[statuses[offset - 1]] then
      return fail('pre_activation_v1_active_status_without_queue')
    end
  elseif status ~= 'completed' and status ~= 'failed' and status ~= 'cancelled' then
    return fail('pre_activation_v1_invalid_status')
  end
end

local server_info = redis.call('INFO', 'server')
local redis_run_id = string.match(server_info, 'run_id:([0-9a-f]+)')
if not redis_run_id then return fail('pre_activation_v1_run_id_missing') end
local current = redis.call('TIME')
local observed_at_ms = current[1] .. string.format('%03d', math.floor(current[2] / 1000))
return cjson.encode({
  sourceVersion = '2',
  indexVersion = 'pre-activation',
  redisRunId = redis_run_id,
  observedAtMs = observed_at_ms,
  queued = queued,
  running = running
})
