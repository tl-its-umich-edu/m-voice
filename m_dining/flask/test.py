import json, os, unittest

import requests
class TestApi(unittest.TestCase):

    def test_main(self):

        HOST = os.getenv("MVOICE_HOST")

        self.assertIsNotNone(HOST, "You must set MVOICE_HOST environment variable to be the server of MVOICE External HOST. For instance: export MVOICE_HOST=mvoice.appspot.com")

        data = ( )

        r = requests.post(url="https://"+HOST, data=data)

        print (r.text)


        # check result from server with expected data
        #self.assertEqual(
        #    result.data,
        #    json.dumps(sent)
        #)

if __name__ == '__main__':
    unittest.main()
