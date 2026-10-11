local prefix = 'inkforge:executions'
local pending_key = prefix .. ':callbacks:pending'
local leased_key = prefix .. ':callbacks:leased'
local rejected_key = prefix .. ':callbacks:rejected'
local quarantine_key = prefix .. ':restore:quarantine'
local active_key = prefix .. ':drain:active'
local version_key = prefix .. ':drain:index-version'
local member_prefix = prefix .. ':'
local maximum_active = 256

local function fail(code)
  return cjson.encode({error = code})
end

local function encode_array(values)
  if #values == 0 then return '[]' end
  return cjson.encode(values)
end

if redis.call('EXISTS', quarantine_key) == 1 then
  return fail('execution_restore_quarantine_present')
end
if redis.call('GET', version_key) ~= '1' then
  return fail('execution_drain_index_version_missing_or_invalid')
end

local active_count = redis.call('ZCARD', active_key)
local callback_count = redis.call('ZCARD', pending_key)
    + redis.call('ZCARD', leased_key)
    + redis.call('ZCARD', rejected_key)
if active_count > maximum_active or callback_count > maximum_active then
  return fail('execution_drain_index_resource_limit')
end

local active_members = redis.call('ZRANGE', active_key, 0, -1, 'WITHSCORES')
local active_seen = {}
local callbacks_seen = {}
local active = {}
local pending = {}
local leased = {}
local rejected = {}

local function callback_membership(member)
  local in_pending = redis.call('ZSCORE', pending_key, member) ~= false
  local in_leased = redis.call('ZSCORE', leased_key, member) ~= false
  local in_rejected = redis.call('ZSCORE', rejected_key, member) ~= false
  local memberships = 0
  if in_pending then memberships = memberships + 1 end
  if in_leased then memberships = memberships + 1 end
  if in_rejected then memberships = memberships + 1 end
  return in_pending, in_leased, in_rejected, memberships
end

for offset = 1, #active_members, 2 do
  local member = active_members[offset]
  local index_score = active_members[offset + 1]
  if active_seen[member] then return fail('execution_active_member_duplicate') end
  active_seen[member] = true
  if string.sub(member, 1, string.len(member_prefix)) ~= member_prefix then
    return fail('execution_active_member_prefix_invalid')
  end
  local step_id = redis.call('HGET', member, 'step_id')
  local accepted_ms = redis.call('HGET', member, 'accepted_ms')
  local state = redis.call('HGET', member, 'state')
  local delivery = redis.call('HGET', member, 'callback_delivery')
  local result_hash = redis.call('HGET', member, 'result_hash')
  local claim_token = redis.call('HGET', member, 'callback_claim_token')
  if not step_id or member ~= member_prefix .. step_id
      or not accepted_ms or not string.match(accepted_ms, '^%d+$')
      or tonumber(index_score) ~= tonumber(accepted_ms) then
    return fail('execution_active_member_binding_invalid')
  end
  local in_pending, in_leased, in_rejected, memberships = callback_membership(member)
  if state == 'accepted' or state == 'started' then
    if delivery ~= 'pending' or result_hash or claim_token or memberships ~= 0 then
      return fail('execution_active_nonterminal_invalid')
    end
    table.insert(active, {id = step_id, acceptedAtMs = accepted_ms})
  elseif state == 'result' or state == 'failure' then
    if not result_hash then return fail('execution_terminal_result_hash_missing') end
    if delivery == 'pending' then
      if memberships ~= 1 or in_rejected
          or (in_leased and not claim_token)
          or (in_pending and claim_token) then
        return fail('execution_pending_callback_binding_invalid')
      end
      local entry = {id = step_id, acceptedAtMs = accepted_ms}
      if in_pending then
        table.insert(pending, entry)
      else
        table.insert(leased, entry)
      end
    elseif delivery == 'rejected' then
      if memberships ~= 1 or not in_rejected or claim_token then
        return fail('execution_rejected_callback_binding_invalid')
      end
      table.insert(rejected, {id = step_id, acceptedAtMs = accepted_ms})
    else
      return fail('execution_delivered_member_left_active')
    end
  else
    return fail('execution_active_state_invalid')
  end
end

local function verify_callback_index(key)
  local members = redis.call('ZRANGE', key, 0, -1)
  for _, member in ipairs(members) do
    if callbacks_seen[member] then return 'execution_callback_member_in_multiple_sets' end
    callbacks_seen[member] = true
    if not active_seen[member] then return 'execution_callback_without_active_member' end
  end
  return nil
end

local pending_error = verify_callback_index(pending_key)
if pending_error then return fail(pending_error) end
local leased_error = verify_callback_index(leased_key)
if leased_error then return fail(leased_error) end
local rejected_error = verify_callback_index(rejected_key)
if rejected_error then return fail(rejected_error) end
if #active + #pending + #leased + #rejected ~= active_count
    or #pending + #leased + #rejected ~= callback_count then
  return fail('execution_drain_index_cardinality_mismatch')
end

local server_info = redis.call('INFO', 'server')
local redis_run_id = string.match(server_info, 'run_id:([0-9a-f]+)')
if not redis_run_id then return fail('execution_redis_run_id_missing') end
local current = redis.call('TIME')
local observed_at_ms = current[1] .. string.format('%03d', math.floor(current[2] / 1000))
return '{'
    .. '"sourceVersion":"2",'
    .. '"indexVersion":"1",'
    .. '"redisRunId":' .. cjson.encode(redis_run_id) .. ','
    .. '"observedAtMs":' .. cjson.encode(observed_at_ms) .. ','
    .. '"active":' .. encode_array(active) .. ','
    .. '"pending":' .. encode_array(pending) .. ','
    .. '"leased":' .. encode_array(leased) .. ','
    .. '"rejected":' .. encode_array(rejected) .. ','
    .. '"quarantined":false'
    .. '}'
