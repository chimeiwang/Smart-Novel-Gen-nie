local prefix = 'inkforge:executions'
local marker_key = prefix .. ':drain:index-version'
local quarantine_key = prefix .. ':restore:quarantine'

local marker = redis.call('GET', marker_key)
if marker then
  if marker == '1' then return 'existing' end
  redis.call('SET', quarantine_key, 'drain-index-version-invalid')
  return 'invalid-version'
end
if redis.call('DBSIZE') ~= 0 then
  redis.call('SET', quarantine_key, 'drain-index-missing-with-execution-data')
  return 'execution-data-present-quarantined'
end
redis.call('SET', marker_key, '1')
return 'initialized'
