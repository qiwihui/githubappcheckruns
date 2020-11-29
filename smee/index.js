const SmeeClient = require('smee-client')

const smee = new SmeeClient({
    source: 'https://smee.io/LgDQ8xrhy0q2GeET',
    target: 'http://localhost:5000/events',
    logger: console
})

const events = smee.start()

// Stop forwarding events
// events.close()