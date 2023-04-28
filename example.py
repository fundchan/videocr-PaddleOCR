from videocr import save_subtitles_to_file, save_tsv_subtitles_to_file

if __name__ == '__main__':
    # save_subtitles_to_file('example_cropped.mp4', 'example.srt', lang='ch', time_start='0:00', time_end='',
    #                        sim_threshold=80, conf_threshold=50, use_fullframe=True, use_gpu=True,
    #                        # Models different from the default mobile models can be downloaded here: https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.3/doc/doc_en/models_list_en.md
    #                        # det_model_dir='<PADDLEOCR DETECTION MODEL DIR>', rec_model_dir='<PADDLEOCR RECOGNITION MODEL DIR>',
    #                        brightness_threshold=210, similar_image_threshold=1000, frames_to_skip=1)

    save_tsv_subtitles_to_file('example_cropped.mp4', 'example.tsv', lang='ch', time_start='0:00', time_end='',
                               sim_threshold=80, conf_threshold=50, use_fullframe=True, use_gpu=True,
                               # Models different from the default mobile models can be downloaded here: https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.3/doc/doc_en/models_list_en.md
                               # det_model_dir='<PADDLEOCR DETECTION MODEL DIR>', rec_model_dir='<PADDLEOCR RECOGNITION MODEL DIR>',
                               brightness_threshold=210, similar_image_threshold=1000, frames_to_skip=1)
