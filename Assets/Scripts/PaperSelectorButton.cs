using UnityEngine;
using UnityEngine.SceneManagement;

namespace PaperCave
{
    public class PaperSelectorButton : MonoBehaviour
    {
        [Header("Nome da pasta do paper")]
        public string paperName;

        [Header("Cena que será aberta")]
        public string sceneName = "PaperScene";

        public void OpenPaper()
        {
            PlayerPrefs.SetString("SelectedPaper", paperName);
            PlayerPrefs.Save();

            SceneManager.LoadScene(sceneName);
        }
    }
}