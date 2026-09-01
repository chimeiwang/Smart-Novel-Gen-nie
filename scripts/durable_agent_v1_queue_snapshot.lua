local prefix = 'inkforge:runs'
local ready_key = prefix .. ':ready'
local processing_key = prefix .. ':processing'
local statuses_key = prefix .. ':statuses'
local queued_index_key = prefix .. ':drain:queued'
local running_index_key = prefix .. ':drain:running'
local version_key = prefix .. ':drain:index-version'
local maximum_active = 256

local function fail(code)
  return cjson.encode({error = code})
end

local function encode_array(values)
  if #values == 0 then return '[]' end
  return cjson.encode(values)
end

if redis.call('GET', version_key) ~= '1' then
  return fail('queue_drain_index_version_missing_or_invalid')
end

local queued_count = redis.call('ZCARD', queued_index_key)
local running_count = redis.call('ZCARD', running_index_key)
if queued_count + running_count > maximum_active then
  return fail('queue_drain_index_resource_limit')
end
if redis.call('ZCARD', ready_key) ~= queued_count
    or redis.call('ZCARD', processing_key) ~= running_count then
  return fail('queue_drain_index_cardinality_mismatch')
end

local seen = {}
local function entries(index_key, queue_key, other_queue_key, expected_status)
  local result = {}
  local values = redis.call('ZRANGE', index_key, 0, -1, 'WITHSCORES')
  for offset = 1, #values, 2 do
    local job_id = values[offset]
    local created_ms = values[offset + 1]
    if seen[job_id] then return nil, 'queue_drain_member_in_multiple_indexes' end
    seen[job_id] = true
    if not string.match(created_ms, '^%d+$')
        or redis.call('HGET', statuses_key, job_id) ~= expected_status
        or not redis.call('ZSCORE', queue_key, job_id)
        or redis.call('ZSCORE', other_queue_key, job_id) then
      return nil, 'queue_drain_member_binding_invalid'
    end
    table.insert(result, {id = job_id, createdAtMs = created_ms})
  end
  return result, nil
end

local queued, queued_error = entries(
  queued_index_key, ready_key, processing_key, 'queued')
if queued_error then return fail(queued_error) end
local running, running_error = entries(
  running_index_key, processing_key, ready_key, 'running')
if running_error then return fail(running_error) end

local server_info = redis.call('INFO', 'server')
local redis_run_id = string.match(server_info, 'run_id:([0-9a-f]+)')
if not redis_run_id then return fail('queue_redis_run_id_missing') end
local current = redis.call('TIME')
local observed_at_ms = current[1] .. string.format('%03d', math.floor(current[2] / 1000))
return '{'
    .. '"sourceVersion":"2",'
    .. '"indexVersion":"1",'
    .. '"redisRunId":' .. cjson.encode(redis_run_id) .. ','
    .. '"observedAtMs":' .. cjson.encode(observed_at_ms) .. ','
    .. '"queued":' .. encode_array(queued) .. ','
    .. '"running":' .. encode_array(running)
    .. '}'
