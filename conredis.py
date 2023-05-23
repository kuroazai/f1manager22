import redis
import pickle

class ConRedis:

    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, db=0,)

    def dump_object_to_redis(self, redis_key, obj):
        # Serialize the object using pickle
        serialized_object = pickle.dumps(obj)

        # Store the serialized object in Redis
        self.r.set(redis_key, serialized_object)

    def retrieve_object_from_redis(self, redis_key):
        # Retrieving the object from Redis
        retrieved_object = self.r.get(redis_key)

        if retrieved_object is not None:
            # Deserialize the object using pickle
            deserialized_object = pickle.loads(retrieved_object)
            return deserialized_object
        else:
            return None
